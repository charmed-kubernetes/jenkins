""" Script for generating HTML output
"""

from kv import KV
from datetime import datetime, timedelta
from pathlib import Path
from collections import OrderedDict
from boto3.dynamodb.conditions import Key
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
        'reports/_build/index.html', bucket.name, 'index-new.html',
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
    table = dynamodb.Table('CIBuilds')
    response = table.scan()
    metadata = OrderedDict()
    for obj in response['Items']:
        db = {}
        db['day'] = datetime.strptime(obj['build_endtime'],
                                      '%Y-%m-%dT%H:%M:%S.%f').strftime('%Y-%m-%d')
        click.echo(db['day'])
        db['job_name'] = obj['job_name']
        if 'test_result' not in obj:
            result_bg_class = ''
        elif obj['test_result'] == 'Fail':
            result_bg_class = 'bg-danger'
        else:
            result_bg_class = 'bg-success'
        db['bg_class'] = result_bg_class
        db['results_file'] = obj['results_file'] if 'results_file' in obj else ''
        if 'job_name' in db and db['job_name'] in metadata:
            metadata[db['job_name']].append(db)
        else:
            metadata[db['job_name']] = [db]
    return metadata

def _gen_rows():
    """ Generates reports
    """
    days = _gen_days()
    metadata = _gen_metadata()
    rows = []
    for jobname, jobs in sorted(metadata.items()):
        sub_item = [jobname]
        for day in days:
            _job = [j
                    for j in jobs
                    if j['day'] == day]
            if _job:
                click.echo(_job)
                sub_item.append(_job[-1])
            else:
                sub_item.append(
                    {'job_name': jobname,
                     'bg_class': ''})
        click.echo(f"Processed: {jobname}")
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
