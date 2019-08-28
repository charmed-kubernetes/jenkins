""" Script for storing build results
"""

from datetime import datetime
from kv import KV
from pathlib import Path
import boto3
import click
import os
import sh
import yaml
from pprint import pformat

db = KV("stats.db")
session = boto3.Session(profile_name="default", region_name="us-east-1")
dynamodb = session.resource("dynamodb")
s3 = session.client("s3")


@click.group()
def cli():
    pass


@cli.command()
def starttime():
    """ Sets a startime timestamp
    """
    db["build_datetime"] = str(datetime.utcnow().isoformat())


@cli.command()
def endtime():
    """ Sets a endtime timestamp
    """
    db["build_endtime"] = str(datetime.utcnow().isoformat())


@cli.command()
@click.option("--fail/--no-fail", default=True)
def test_result(fail):
    """ Sets test result
    """
    result = True
    if fail:
        result = False

    db["test_result"] = result


@cli.command()
def set_meta():
    """ Sets metadata information
    """
    env = os.environ.copy()
    db["job_name"] = env["JOB_NAME"]
    db["build_number"] = env["BUILD_NUMBER"]
    db["node_name"] = env["NODE_NAME"]
    db["build_tag"] = env["BUILD_TAG"]
    db["workspace"] = env["WORKSPACE"]
    db["git_commit"] = env["GIT_COMMIT"]
    db["git_url"] = env["GIT_URL"]
    db["git_branch"] = env.get("GIT_BRANCH", "master")


@cli.command()
@click.option("--table", default="CIBuilds")
def save_meta(table):
    """ Saves metadata to yaml
    """
    click.echo("Saving build to database")
    click.echo("Build Data:\n{}\n".format(pformat(dict(db))))
    table = dynamodb.Table(table)
    table.put_item(Item=dict(db))


@cli.command()
@click.option("--bucket", required=True, help="s3 bucket to use", default="jenkaas")
@click.option("--key-id", default="last_file", help="key to associate with upload")
@click.argument("results-file")
def push(bucket, results_file, key_id):
    """ pushes files to s3
    """
    results_file = Path(results_file)
    if not results_file.exists():
        return
    current_date = datetime.now().strftime("%Y-%m-%d")
    env = os.environ.copy()
    s3_path = Path(env["JOB_NAME"]) / current_date / env["BUILD_NUMBER"] / results_file
    s3.upload_file(str(results_file), bucket, str(s3_path))
    db[key_id] = str(s3_path)


if __name__ == "__main__":
    cli()
