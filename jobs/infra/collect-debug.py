""" Script for storing build results
"""

import click
import sh
import os
import attr
from datetime import datetime
from pathlib import Path

s3 = sh.aws.bake('s3 --profile s3', _env=os.environ.copy())

@click.group()
def cli():
    pass

@cli.command
@click.option('--bucket', required=True, help="s3 bucket to use",
              default="jenkaas")
@click.option('--results-file', required=True,
              help="Path to results file")
def results(bucket, results_file):
    """ pushes cdk field agent and sets build result
    """
    results_file = Path(results_file)
    current_date = datetime.now().strftime('%Y-%m-%d')
    env = os.environ.copy()
    s3_path = f"s3://{bucket}/{env['JOB_NAME']}/{current_date}/{env['BUILD_NUMBER']}/{results_file.parent}"
    s3.cp(str(results_file), s3_path)
