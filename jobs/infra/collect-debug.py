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

db = KV('stats.db')

@click.group()
def cli():
    pass


@cli.command()
def starttime():
    """ Sets a startime timestamp
    """
    db['starttime'] = str(datetime.now())

@cli.command()
def endtime():
    """ Sets a endtime timestamp
    """
    db['endtime'] = str(datetime.now())

@cli.command()
@click.option('--fail/--no-fail', default=True)
def test_result(fail):
    """ Sets test result
    """
    result = 'Pass'
    if fail:
        result = 'Fail'

    db['test-result'] = result


@cli.command()
def set_meta():
    """ Sets metadata information
    """
    env = os.environ.copy()
    db['job-name'] = env['JOB_NAME']
    db['build-number'] = env['BUILD_NUMBER']
    db['node-name'] = env['NODE_NAME']
    db['build-tag'] = env['BUILD_TAG']
    db['workspace'] = env['WORKSPACE']
    db['git-commit'] = env['GIT_COMMIT']
    db['git-url'] = env['GIT_URL']
    db['git-branch'] = env['GIT_BRANCH']


@cli.command()
@click.option('--filename', default='meta.yaml')
def save_meta(filename):
    """ Saves metadata to yaml
    """
    filename = Path(filename)
    data = yaml.dump(dict(db), default_flow_style=False)
    filename.write_text(data, encoding='utf-8')


@cli.command()
@click.option('--bucket', required=True, help="s3 bucket to use",
              default="jenkaas")
@click.option('--key-id', default="last_file", help="key to associate with upload")
@click.argument('results-file')
def push(bucket, results_file, key_id):
    """ pushes cdk field agent and sets build result
    """
    session = boto3.Session(profile_name='default')
    s3 = session.client('s3')
    results_file = Path(results_file)
    current_date = datetime.now().strftime('%Y-%m-%d')
    env = os.environ.copy()
    s3_path = Path(env['JOB_NAME']) / current_date / env['BUILD_NUMBER'] / results_file
    s3.upload_file(str(results_file), bucket, str(s3_path))
    db[f"resource.{key_id}"] = s3_path


if __name__ == "__main__":
    cli()
