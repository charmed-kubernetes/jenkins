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
from pathlib import Path
from pprint import pformat, pprint
from cilib import log, run, html

session = boto3.Session(region_name="us-east-1")
s3 = session.resource("s3")
dynamodb = session.resource("dynamodb")
bucket = s3.Bucket("jenkaas")

OBJECTS = bucket.objects.all()

SERIES = ["focal", "bionic", "xenial"]


def get_all_s3_prefixes(numdays=30):
    """ Grabs all s3 prefixes for at most `numdays`
    """
    date_of_last_30 = datetime.today() - timedelta(days=numdays)
    date_of_last_30 = date_of_last_30.strftime("%Y-%m-%d")
    output = run.capture(f"aws s3api list-objects-v2 --bucket jenkaas --query 'Contents[?LastModified > `{date_of_last_30}`]'", shell=True)
    return output

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
                items.append(item)

        log.info("Storing local copy")
        storage_p.write_bytes(dill.dumps(items))
    return items


def _gen_metadata(items):
    """ Generates metadata
    """

    db = OrderedDict()
    debug_host_url = "https://jenkaas.s3.amazonaws.com"

    for obj in items:
        if "build_endtime" not in obj:
            continue
        if 'job_id' not in obj:
            continue

        day = datetime.strptime(obj["build_endtime"], "%Y-%m-%dT%H:%M:%S.%f")
        date_of_last_30 = datetime.today() - timedelta(days=30)
        if day < date_of_last_30:
            continue
        day = day.strftime("%Y-%m-%d")

        obj["debug_host"] = debug_host_url
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

        # set columbo results
        if "columbo_results" in obj:
            _gen_columbo(obj)

        if day not in db[job_name]:
            db[job_name][day] = []
        db[job_name][day].append(obj)
    return db

def _gen_columbo(obj):
    has_index = requests.get(f"{obj['debug_host']}/{obj['job_id']}/index.html")
    if has_index.ok:
        log.info(f"Report already generated for {obj['job_id']}, skipping.")
        return

    report_url = f"{obj['debug_host']}/{obj['job_id']}/columbo-report.json"
    log.info(f"Processing {report_url}")
    has_index = requests.get(report_url, stream=True)
    if not has_index.ok:
        log.info(f"- no report file, skipping")
        return
    if int(has_index.headers['Content-length']) >= 1048576:
        log.info("- Columbo report to big, skipping")
        run.cmd_ok(f"aws s3 rm s3://jenkaas/{obj['job_id']}/columbo-report.json", shell=True)
        return

    tmpl = html.template("columbo.html")
    run.cmd_ok(f"aws s3 cp s3://jenkaas/{obj['job_id']}/columbo-report.json columbo-report.json", shell=True)
    columbo_report_p = Path('columbo-report.json')
    results = json.loads(columbo_report_p.read_text())
    context = {
        "obj":obj,
        "columbo_results": results
    }
    rendered = tmpl.render(context)
    html_p = Path(f"{obj['job_id']}-columbo.html")
    html_p.write_text(rendered)
    run.cmd_ok(f"aws s3 cp {obj['job_id']}-columbo.html s3://jenkaas/{obj['job_id']}/index.html", shell=True)
    run.cmd_ok(f"rm -rf {html_p}")

def _gen_rows():
    """ Generates reports
    """
    days = _gen_days()
    data = get_data()
    metadata = _gen_metadata(data)
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
    log.info(response["Items"])


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
