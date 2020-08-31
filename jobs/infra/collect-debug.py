""" Script for storing build results
"""

from datetime import datetime
from pathlib import Path
import boto3
import click
import os
import json
import operator
from pprint import pformat
from kv import KV

db = KV("metadata.db")
session = boto3.Session(profile_name="default", region_name="us-east-1")
dynamodb = session.resource("dynamodb")
s3 = session.client("s3")


@click.group()
def cli():
    pass


@cli.command()
@click.option("--table", default="CIBuilds")
def save_meta(table):
    """Saves metadata to dynamo"""
    click.echo("Saving build to database")
    table = dynamodb.Table(table)
    table.put_item(Item=dict(db))
    click.echo("Build Data:\n{}\n".format(pformat(dict(db))))


@cli.command()
@click.argument("db_key")
@click.argument("db_val")
def set_key(db_key, db_val):
    """sets db key/val"""
    db[db_key] = db_val


@cli.command()
@click.option("--bucket", required=True, help="s3 bucket to use", default="jenkaas")
@click.argument("db_key")
@click.argument("results-file", nargs=-1)
def push(bucket, db_key, results_file):
    """pushes files to s3"""
    result_path_objs = []
    for r_file in results_file:
        r_file = Path(r_file)
        if not r_file.exists():
            continue
        result_path_objs.append((r_file, r_file.stat().st_mtime))

    newest_result_file = max(result_path_objs, key=operator.itemgetter(1))[0]
    current_date = datetime.now().strftime("%Y/%m/%d")
    env = os.environ.copy()
    if "job_name_custom" in db:
        job_name = db["job_name_custom"]
    else:
        job_name = db["job_name"]
    s3_path = (
        Path(job_name)
        / current_date
        / db["build_number"]
        / db["build_endtime"]
        / newest_result_file
    )
    s3.upload_file(str(newest_result_file), bucket, str(s3_path))
    db[db_key] = str(s3_path)


if __name__ == "__main__":
    cli()
