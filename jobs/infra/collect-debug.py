""" Script for storing build results
"""

from datetime import datetime
from pathlib import Path
import boto3
import click
import os
import json
from pprint import pformat
from kv import KV

db = KV("metadata.db")
session = boto3.Session(profile_name="default", region_name="us-east-1")
dynamodb = session.resource("dynamodb")
s3 = session.client("s3")


@click.group()
def cli():
    pass


def set_meta():
    """ Sets metadata information
    """
    env = os.environ.copy()
    db["job_name"] = env.get("JOB_NAME", "yoink")
    db["build_number"] = env.get("BUILD_NUMBER", 0)
    db["build_tag"] = env.get("BUILD_TAG", "master")
    db["workspace"] = env.get("WORKSPACE", "n/a")
    db["git_commit"] = env.get("GIT_COMMIT", "n/a")
    db["git_url"] = env.get("GIT_URL", "n/a")
    db["git_branch"] = env.get("GIT_BRANCH", "master")


@cli.command()
@click.option("--table", default="CIBuilds")
@click.argument("results-file")
def save_meta(table, results_file):
    """ Saves metadata to dynamo
    """
    click.echo("Saving build to database")
    metadata = Path(results_file)
    if metadata.exists():
        _db = json.loads(metadata.read_text(encoding="utf8"))
        db.update(_db)
        click.echo("Build Data:\n{}\n".format(pformat(dict(db))))
        table = dynamodb.Table(table)
        table.put_item(Item=dict(db))


@cli.command()
@click.argument("db_key")
@click.argument("db_val")
def set_key(db_key, db_val):
    """ sets db key/val
    """
    db[db_key] = db_val


@cli.command()
@click.option("--bucket", required=True, help="s3 bucket to use", default="jenkaas")
@click.argument("db_key")
@click.argument("results-file")
def push(bucket, db_key, results_file):
    """ pushes files to s3
    """
    results_file = Path(results_file)
    if not results_file.exists():
        return
    current_date = datetime.now().strftime("%Y/%m/%d")
    env = os.environ.copy()
    s3_path = Path(env["JOB_NAME"]) / current_date / env["BUILD_NUMBER"] / results_file
    s3.upload_file(str(results_file), bucket, str(s3_path))
    db[db_key] = str(s3_path)


if __name__ == "__main__":
    cli()
