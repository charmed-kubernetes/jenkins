""" Script for generating HTML output
"""

from kv import KV
import attr
import box
from datetime import datetime, timedelta
from pathlib import Path
from collections import OrderedDict
from boto3.dynamodb.conditions import Key, Attr
import boto3
import click
import os
import sh
import mimetypes
from staticjinja import Site

session = boto3.Session(region_name='us-east-1')
s3 = session.resource('s3')
dynamodb = session.resource('dynamodb')
bucket = s3.Bucket('jenkaas')

OBJECTS = bucket.objects.all()


def upload_html():
    mimetype, _ = mimetypes.guess_type('reports/_build/index.html')
    s3.meta.client.upload_file(
        'reports/_build/index.html', bucket.name, 'index.html',
        ExtraArgs={'ContentType': mimetype})

def download_file(key, filename):
    """ Downloads file
    """
    s3.meta.client.download_file(bucket.name, key, filename)

def _parent_dirs():
    """ Returns list of paths
    """
    items = set()
    for obj in OBJECTS:
        if obj.key != 'index.html':
            items.add(obj.key)
    return list(sorted(items))

def _gen_days(numdays=30):
    """ Generates last numdays, date range
    """
    base = datetime.today()
    date_list = [(base - timedelta(
        days=x)).strftime('%Y-%m-%d') for x in range(0, numdays)]
    return date_list

def _gen_metadata():
    """ Generates metadata
    """
    click.echo("Generating metadata...")
    items = []
    table = dynamodb.Table('CIBuilds')

    # Required because only 1MB are returned
    # See: https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/GettingStarted.Python.04.html
    response = table.scan()
    for item in response['Items']:
        items.append(item)
    while 'LastEvaluatedKey' in response:
        response = table.scan(ExclusiveStartKey=response['LastEvaluatedKey'])
        for item in response['Items']:
            items.append(item)
    metadata = OrderedDict()
    db = OrderedDict()
    for obj in items:
        obj = box.Box(obj)
        if obj.job_name not in db:
            db[obj.job_name] = {}

        if 'build_endtime' not in obj:
            continue

        if 'test_result' not in obj:
            result_bg_class = 'bg-light'
        elif obj['test_result'] == 'Fail':
            result_bg_class = 'bg-danger'
        else:
            result_bg_class = 'bg-success'

        obj.bg_class = result_bg_class

        try:
            day = datetime.strptime(obj['build_endtime'],
                                    '%Y-%m-%dT%H:%M:%S.%f').strftime('%Y-%m-%d')
        except:
            day = datetime.strptime(obj['build_endtime'],
                                    '%Y-%m-%d %H:%M:%S.%f').strftime('%Y-%m-%d')

        if day not in db[obj.job_name]:
            db[obj.job_name][day] = []
        db[obj.job_name][day].append(obj)
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
            if day in jobdays:
                max_build_number = max(
                    int(item['build_number']) for item in jobdays[day])
                for job in jobdays[day]:
                    if job['build_number'] == str(max_build_number):
                        sub_item.append(job)
            else:
                sub_item.append(
                    {'job_name': jobname,
                     'bg_class': ''})
        rows.append(sub_item)
    return rows


@click.group()
def cli():
    pass

@cli.command()
def list():
    """ List keys in dynamodb
    """
    table = dynamodb.Table('CIBuilds')
    response = table.scan()
    click.echo(response['Items'])

@cli.command()
def migrate():
    """ Migrate from older stats.db
    """
    table = dynamodb.Table('CIBuilds')
    for item in OBJECTS:
        if 'stats.db' in item.key:
            download_file(item.key, 'stats.db')
            obj = {}
            db = KV('stats.db')
            click.echo(f'Processing {db["build-tag"]}')
            try:
                obj['build_datetime'] = db['starttime']
                obj['build_endtime'] = db['endtime']
                obj['job_name'] = db['job-name']
                obj['build_number'] = db['build-number']
                obj['node_name'] = db['node-name']
                obj['build_tag'] = db['build-tag']
                obj['git_commit'] = db['git-commit']
                obj['git_url'] = db['git-url']
                obj['git_branch'] = db['git-branch']
                obj['test_result'] = db['test-result']
                obj['workspace'] = db['workspace']
                table.put_item(Item=obj)
            except:
                continue

@cli.command()
def build():
    """ Generate a report
    """
    context = {
        'rows': _gen_rows(),
        'headers': [datetime.strptime(day, '%Y-%m-%d').strftime('%m-%d')
                    for day in _gen_days()],
        'modified': datetime.now()
    }
    site = Site.make_site(
        contexts=[('index.html', context)],
        outpath='reports/_build')
    site.render()
    upload_html()

if __name__ == "__main__":
    cli()
