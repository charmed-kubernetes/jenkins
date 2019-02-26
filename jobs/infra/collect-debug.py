""" Script for storing build results
"""

import click
import boto3
import sh
import os
from datetime import datetime
from pathlib import Path

@click.group()
def cli():
    pass

@cli.command()
@click.option('--bucket', required=True, help="s3 bucket to use",
              default="jujubigdata")
@click.argument('results-file')
def push(bucket, results_file):
    """ pushes cdk field agent and sets build result
    """
    session = boto3.Session(profile_name='s3')
    s3 = session.client('s3')
    results_file = Path(results_file)
    current_date = datetime.now().strftime('%Y-%m-%d')
    env = os.environ.copy()
    s3_path = f"k8sci/{env['JOB_NAME']}/{current_date}/{env['BUILD_NUMBER']}/{results_file}"
    s3.upload_file(str(results_file), 'jujubigdata', s3_path)


if __name__ == "__main__":
    cli()
