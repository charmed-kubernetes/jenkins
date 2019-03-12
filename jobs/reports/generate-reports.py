""" Script for generating HTML output
"""

from kv import KV
from datetime import datetime, timedelta
from pathlib import Path
from collections import OrderedDict
import boto3
import click
import os
import sh
import mimetypes
from staticjinja import Site

s3 = boto3.resource('s3')
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

def _get_field_agent_path(dir_key):
    """ Grab cdk field agent file for key
    """
    for obj in OBJECTS:
        path_obj = Path(obj.key)
        if path_obj.parent == dir_key and 'results' in path_obj.parts[-1]:
            return obj.key
    return None

def _gen_metadata():
    """ Generates metadata
    """
    click.echo("Generating metadata...")
    metadata = OrderedDict()
    for obj in OBJECTS:
        path_obj = Path(obj.key)
        parts = path_obj.parts
        if parts[-1] == 'stats.db':
            download_file(obj.key, parts[-1])
            db = KV(parts[-1])
            db['day'] = parts[1]
            if 'job-name' not in db:
                db['job-name'] = parts[0]
            if 'test-result' not in db:
                result_bg_class = ''
            elif db['test-result'] == 'Fail':
                result_bg_class = 'bg-danger'
            else:
                result_bg_class = 'bg-success'
            db['bg-class'] = result_bg_class
            cdk_field_agent = _get_field_agent_path(path_obj.parent)
            if cdk_field_agent:
                db['cdk-field-agent'] = cdk_field_agent
            if 'job-name' in db and db['job-name'] in metadata:
                metadata[db['job-name']].append(db)
            else:
                metadata[db['job-name']] = [db]
    return metadata

def _gen_rows():
    """ Generates reports
    """
    days = _gen_days()
    metadata = _gen_metadata()
    rows = []
    for jobname, jobs in metadata.items():
        sub_item = [jobname]
        for day in days:
            _job = [j
                    for j in jobs
                    if j['day'] == day]
            if _job:
                sub_item.append(_job[-1])
            else:
                sub_item.append(
                    {'job-name': jobname,
                     'bg-class': ''})
        click.echo(f"Processed: {jobname}")
        rows.append(sub_item)
    return rows


@click.group()
def cli():
    pass

@cli.command()
def list():
    """ List keys in bucket
    """
    for obj in OBJECTS:
        click.echo(obj)

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
