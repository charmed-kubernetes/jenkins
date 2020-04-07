""" Script for generating HTML output
"""

from datetime import datetime, timedelta
from collections import OrderedDict
from boto3.dynamodb.conditions import Key, Attr
import boto3
import click
import sh
from pathlib import Path
from pprint import pformat
from cilib import log, run, html

session = boto3.Session(region_name="us-east-1")
s3 = session.resource("s3")
dynamodb = session.resource("dynamodb")
bucket = s3.Bucket("jenkaas")

OBJECTS = bucket.objects.all()

SERIES = ["focal", "bionic", "xenial"]


def _parent_dirs():
    """ Returns list of paths
    """
    items = set()
    for obj in OBJECTS:
        if obj.key != "index.html":
            items.add(obj.key)
    return list(sorted(items))


def _gen_days(numdays=30):
    """ Generates last numdays, date range
    """
    base = datetime.today()
    date_list = [
        (base - timedelta(days=x)).strftime("%Y-%m-%d") for x in range(0, numdays)
    ]
    return date_list


def _gen_metadata():
    """ Generates metadata
    """
    log.info("Generating metadata...")
    items = []
    table = dynamodb.Table("CIBuilds")

    # Required because only 1MB are returned
    # See: https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/GettingStarted.Python.04.html
    response = table.scan()
    for item in response["Items"]:
        items.append(item)
    while "LastEvaluatedKey" in response:
        response = table.scan(ExclusiveStartKey=response["LastEvaluatedKey"])
        for item in response["Items"]:
            items.append(item)
    db = OrderedDict()
    for obj in items:
        if "validate" not in obj["job_name"]:
            continue

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

        if "build_endtime" not in obj:
            continue

        if "test_result" not in obj:
            result_bg_class = "bg-light"
            result_btn_class = "btn-light"
        elif not obj["test_result"] or int(obj["test_result"]) == 0:
            result_bg_class = "bg-danger"
            result_btn_class = "btn-danger"
        else:
            result_btn_class = "btn-success"
            result_bg_class = "bg-success"

        obj["bg_class"] = result_bg_class
        obj["btn_class"] = result_btn_class
        try:
            day = datetime.strptime(obj["build_endtime"], "%Y-%m-%dT%H:%M:%S.%f")
        except:
            day = datetime.strptime(obj["build_endtime"], "%Y-%m-%d %H:%M:%S.%f")

        date_of_last_30 = datetime.today() - timedelta(days=30)
        if day < date_of_last_30:
            continue
        day = day.strftime("%Y-%m-%d")

        # set obj url
        debug_host_url = "https://jenkaas.s3.amazonaws.com/"
        build_log = obj.get("build_log", None)
        if build_log:
            build_log = str(Path(obj["build_log"]).parent)
        obj["debug_url"] = f"{debug_host_url}" f"{obj['job_name']}/" f"{build_log}"

        if day not in db[job_name]:
            db[job_name][day] = []
        db[job_name][day].append(obj)
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
def list():
    """ List keys in dynamodb
    """
    table = dynamodb.Table("CIBuilds")
    response = table.scan()
    click.echo(response["Items"])


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


if __name__ == "__main__":
    cli()
