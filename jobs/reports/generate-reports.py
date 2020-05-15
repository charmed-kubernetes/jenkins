""" Script for generating HTML output
"""

from datetime import datetime, timedelta
from collections import OrderedDict
from boto3.dynamodb.conditions import Key, Attr
import boto3
import click
import sh
import json
import uuid
import requests
import dill
import os
from pathos.threading import ThreadPool
from pathlib import Path
from pprint import pformat, pprint
from cilib import log, run, html
from prettytable import PrettyTable

session = boto3.Session(region_name="us-east-1")
s3 = session.resource("s3")
dynamodb = session.resource("dynamodb")
bucket = s3.Bucket("jenkaas")

OBJECTS = bucket.objects.all()

SERIES = ["focal", "bionic", "xenial"]

REPORT_HOST = "https://jenkaas.s3.amazonaws.com"


class Storage:
    def __init__(self, numdays=30):
        self.objects = self.get_all_s3_prefixes(numdays)

    def get_all_s3_prefixes(self, numdays=30):
        """ Grabs all s3 prefixes for at most `numdays`
        """
        date_of_last = datetime.today() - timedelta(days=numdays)
        date_of_last = date_of_last.strftime("%Y-%m-%d")
        output = run.capture(
            f"aws s3api list-objects-v2 --bucket jenkaas --query 'Contents[?LastModified > `{date_of_last}`]'",
            shell=True,
        )
        if output.ok:
            return json.loads(output.stdout.decode())
        return []

    @property
    def reports(self):
        """ Return mapping of report files
        """
        _report_map = {}
        for item in self.objects:
            key_p = Path(item["Key"])
            if key_p.parent in _report_map:
                _report_map[key_p.parent].append((key_p.name, int(item["Size"])))
            else:
                _report_map[key_p.parent] = [(key_p.name, int(item["Size"]))]
        return _report_map


def has_file(filename, files):
    return any([name == filename for name, _ in files])


def build_columbo_reports(data):
    prefix_id, files = data
    has_columbo = [
        (name, size) for name, size in files if name == "columbo-report.json"
    ]

    if not has_columbo:
        log.debug(f"{prefix_id} :: no report found, skipping")
        return

    name, size = has_columbo[0]
    if size >= 1048576:
        log.debug(f"{prefix_id} :: columbo report to big, skipping")
        return

    has_index = requests.get(f"{REPORT_HOST}/{prefix_id}/columbo.html")
    if has_index.ok:
        log.debug(f"Report already generated for {prefix_id}, skipping.")
        return

    obj = {}
    has_metadata = requests.get(f"{REPORT_HOST}/{prefix_id}/metadata.json")
    if has_metadata.ok:
        log.info(f"{prefix_id} :: grabbing metadata for report")
        try:
            obj = has_metadata.json()
        except json.decoder.JSONDecodeError:
            return

    has_artifacts = requests.get(f"{REPORT_HOST}/{prefix_id}/artifacts.tar.gz")
    if has_artifacts.ok:
        log.debug(f"{prefix_id} :: found artifacts")
        obj["artifacts"] = f"{REPORT_HOST}/{prefix_id}/artifacts.tar.gz"

    log.info(f"{prefix_id} :: processing report {name} ({size})")

    tmpl = html.template("columbo.html")
    columbo_results = requests.get(f"{REPORT_HOST}/{prefix_id}/{name}").json()
    context = {"obj": obj, "columbo_results": columbo_results}
    rendered = tmpl.render(context)
    html_p = Path(f"{prefix_id}-columbo.html")
    html_p.write_text(rendered)
    run.cmd_ok(
        f"aws s3 cp {prefix_id}-columbo.html s3://jenkaas/{prefix_id}/columbo.html",
        shell=True,
    )
    run.cmd_ok(f"rm -rf {html_p}")


def _gen_days(numdays=30):
    """ Generates last numdays, date range
    """
    base = datetime.today()
    date_list = [
        (base - timedelta(days=x)).strftime("%Y-%m-%d") for x in range(0, numdays)
    ]
    return date_list


def get_data():
    storage_p = Path("storage_dill.pkl")
    log.info("Generating metadata...")
    items = []

    if storage_p.exists():
        log.info("Loading local copy")
        items = dill.loads(storage_p.read_bytes())
    else:
        log.info("Pulling from dynamo")
        table = dynamodb.Table("CIBuilds")

        # Required because only 1MB are returned
        # See: https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/GettingStarted.Python.04.html
        response = table.scan()
        for item in response["Items"]:
            items.append(item)
        while "LastEvaluatedKey" in response:
            response = table.scan(ExclusiveStartKey=response["LastEvaluatedKey"])
            for item in response["Items"]:
                if "build_endtime" not in item:
                    continue
                day = datetime.strptime(item["build_endtime"], "%Y-%m-%dT%H:%M:%S.%f")
                date_of_last_30 = datetime.today() - timedelta(days=30)
                if "job_id" not in item:
                    continue
                if day < date_of_last_30:
                    continue
                log.debug(f"Adding record {item}")
                items.append(item)
        log.info("Storing local copy")
        storage_p.write_bytes(dill.dumps(items))
    return items


def _gen_metadata():
    """ Generates metadata
    """
    _storage = Storage()
    db = OrderedDict()
    debug_host_url = "https://jenkaas.s3.amazonaws.com"

    def _download_metadata(item):
        prefix_id, files = item
        has_metadata = has_file("metadata.json", files)
        if not has_metadata:
            log.debug(f"{prefix_id} :: missing metadata, skipping")
            return

        metadata = requests.get(f"{REPORT_HOST}/{prefix_id}/metadata.json")
        try:
            obj = metadata.json()
        except json.decoder.JSONDecodeError:
            return
        log.info(f"Storing {prefix_id} metadata")
        try:
            Path(f"metadatas/{prefix_id}-metadata.json").write_text(json.dumps(obj))
        except FileNotFoundError:
            return

    metadatas = Path("metadatas")
    if not metadatas.exists():
        os.mkdir("metadatas")

    pool = ThreadPool()
    pool.map(
        _download_metadata,
        [(prefix_id, files) for prefix_id, files in _storage.reports.items()],
    )

    for item in metadatas.glob("*.json"):
        obj = json.loads(item.read_text())

        prefix_id = obj["job_id"]
        if "build_endtime" not in obj:
            continue
        if "job_id" not in obj:
            continue

        day = datetime.strptime(obj["build_endtime"], "%Y-%m-%dT%H:%M:%S.%f")
        date_of_last_30 = datetime.today() - timedelta(days=30)
        if day < date_of_last_30:
            continue
        day = day.strftime("%Y-%m-%d")
        log.info(
            f"{prefix_id} :: grabbing metadata for {obj['job_name']} @ {day} report"
        )

        obj["debug_host"] = debug_host_url
        if "validate" not in obj["job_name"]:
            continue

        obj["artifacts"] = f"{REPORT_HOST}/{prefix_id}/artifacts.tar.gz"
        obj["index"] = f"{REPORT_HOST}/{prefix_id}/index.html"
        obj["columbo_results"] = f"{REPORT_HOST}/{prefix_id}/columbo.html"

        job_name = obj["job_name"]
        if "snap_version" in obj:
            job_name = f"{job_name}-{obj['snap_version']}"
        elif "juju_version" in obj:
            job_name = f"{job_name}-juju-{obj['juju_version']}"

        if "job_name_custom" in obj:
            job_name = obj["job_name_custom"]

        if not any(ser in job_name for ser in SERIES):
            continue

        if job_name not in db:
            db[job_name] = {}

        if "test_result" not in obj:
            result_bg_class = "bg-light"
            result_btn_class = "btn-light"
            result_bg_color = "#d4dee8!important;"
        elif not obj["test_result"] or int(obj["test_result"]) == 0:
            result_bg_class = "bg-danger"
            result_btn_class = "btn-danger"
            result_bg_color = "#ff0018!important;"
        else:
            result_btn_class = "btn-success"
            result_bg_class = "bg-success"
            result_bg_color = "#00cc00!important;"

        obj["bg_class"] = result_bg_class
        obj["btn_class"] = result_btn_class
        obj["bg_color"] = result_bg_color

        if day not in db[job_name]:
            db[job_name][day] = []
        db[job_name][day].append(obj)
    Path("index.json").write_text(json.dumps(db))
    return db


def _gen_rows():
    """ Generates reports
    """
    days = _gen_days()
    metadata = _gen_metadata()
    rows = []
    for jobname, jobdays in sorted(metadata.items()):
        sub_item = [jobname]
        for day in days:
            try:
                dates_to_test = [
                    datetime.strptime(obj["build_endtime"], "%Y-%m-%dT%H:%M:%S.%f")
                    for obj in jobdays[day]
                ]
                max_date_for_day = max(dates_to_test)
                log.info(f"Testing {max_date_for_day}")
                for job in jobdays[day]:
                    _day = datetime.strptime(
                        job["build_endtime"], "%Y-%m-%dT%H:%M:%S.%f"
                    )
                    log.info(f"{_day} == {max_date_for_day}")
                    if _day == max_date_for_day:
                        sub_item.append(job)
            except:
                sub_item.append(
                    {
                        "job_name": jobname,
                        "bg_class": "",
                        "build_endtime": day,
                        "build_datetime": day,
                    }
                )
        rows.append(sub_item)
    return rows


@click.group()
def cli():
    pass


@cli.command()
@click.option("--max-days", help="Max number of previous days to report on", default=10)
@click.option("--job-filter", help="Job to filter on")
def summary(max_days, job_filter):
    """ Get summary of last X days
    """
    obj = Storage(numdays=int(max_days))
    table = PrettyTable()
    table.field_names = ["Job", "Test Result", "Datetime"]
    table.align = "l"

    for prefix_id, files in obj.reports.items():
        has_metadata = has_file("metadata.json", files)
        if not has_metadata:
            log.debug(f"{prefix_id} :: missing metadata, skipping")
            continue

        metadata = requests.get(f"{REPORT_HOST}/{prefix_id}/metadata.json")
        try:
            metadata = metadata.json()
        except json.decoder.JSONDecodeError:
            continue

        job_name = metadata.get("job_name_custom", metadata["job_name"])
        if job_filter and job_filter not in job_name:
            continue

        try:
            table.add_row(
                [
                    job_name,
                    "PASS" if metadata["test_result"] else "FAIL",
                    metadata["build_endtime"],
                ]
            )
        except KeyError:
            click.echo(metadata)
    click.echo(table)


@cli.command()
def list():
    """ List keys in dynamodb
    """
    table = dynamodb.Table("CIBuilds")
    response = table.scan()
    log.info(response["Items"])


@cli.command()
def migrate():
    """ Migrate dynamodb data
    """
    data = get_data()

    def _migrate(obj):
        if "build_endtime" not in obj:
            return

        day = datetime.strptime(obj["build_endtime"], "%Y-%m-%dT%H:%M:%S.%f")
        date_of_last_30 = datetime.today() - timedelta(days=30)
        if day < date_of_last_30:
            return

        if "job_id" not in obj:
            return

        job_id = obj["job_id"]
        has_metadata = requests.get(f"{REPORT_HOST}/{job_id}/metadata.json")
        if has_metadata.ok:
            log.debug(
                f"{job_id} :: metadata exists, skipping migration of {obj['job_name']} @ {day}"
            )
            return

        metadata_p = Path(f"{job_id}-metadata.json")
        metadata_p.write_text(json.dumps(obj))
        log.info(f"Migrating {job_id} :: {obj['job_name']} @ {day} :: to metadata.json")
        run.cmd_ok(
            f"aws s3 cp {job_id}-metadata.json s3://jenkaas/{job_id}/metadata.json",
            shell=True,
        )
        run.cmd_ok(f"rm -rf {job_id}-metadata.json", shell=True)

    pool = ThreadPool()
    pool.map(_migrate, data)


@cli.command()
def columbo():
    """ Update columbo reports
    """
    obj = Storage()
    pool = ThreadPool()
    pool.map(
        build_columbo_reports,
        [(prefix_id, files) for prefix_id, files in obj.reports.items()],
    )


@cli.command()
def build():
    """ Generate a report
    """
    tmpl = html.template("index.html")

    ci_results_context = {
        "rows": _gen_rows(),
        "headers": [
            datetime.strptime(day, "%Y-%m-%d").strftime("%m-%d") for day in _gen_days()
        ],
        "modified": datetime.now(),
    }
    rendered = tmpl.render(ci_results_context)
    index_html_p = Path("index.html")
    index_html_p.write_text(rendered)
    run.cmd_ok("aws s3 cp index.html s3://jenkaas/index.html", shell=True)
    run.cmd_ok("aws s3 cp index.json s3://jenkaas/index.json", shell=True)


if __name__ == "__main__":
    cli()
