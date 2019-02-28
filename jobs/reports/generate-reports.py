""" Script for generating HTML output
"""

from datetime import datetime, timedelta
from pathlib import Path
from collections import OrderedDict
import boto3
import click
import os
import sh
import yaml
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
            items.add(Path(obj.key).parts[0])
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
    metadata = OrderedDict()
    for obj in OBJECTS:
        if obj.key == 'index.html':
            continue
        if 'meta.yaml' not in obj.key:
            continue
        parts = Path(obj.key).parts
        day = parts[1]
        download_file(obj.key, parts[-1])
        output = yaml.load(Path(parts[-1]).read_text(encoding='utf-8'))
        if 'job-name' not in output:
            continue
        output['day'] = day
        if 'test-result' not in output:
            result_bg_class = 'bg-secondary'
        elif output['test-result'] == 'Fail':
            result_bg_class = 'bg-danger'
        else:
            result_bg_class = 'bg-success'
        output['bg-class'] = result_bg_class
        if output['job-name'] in metadata:
            metadata[output['job-name']].append(output)
        else:
            metadata[output['job-name']] = [output]
    return metadata

def _gen_rows():
    """ Generates reports
    """
    days = _gen_days()
    metadata = _gen_metadata()
    rows = []
    for jobname, job in metadata.items():
        sub_item = [jobname]
        for day in days:
            for j in job:
                if j['day'] == day:
                    sub_item.append(j)
                else:
                    sub_item.append({'bg-class': ''})
        rows.append(sub_item)
    return rows


@click.group()
def cli():
    pass

@cli.command()
def build():
    """ Generate a report
    """
    context = {
        'rows': _gen_rows(),
        'headers': _gen_days()
    }
    site = Site.make_site(
        contexts=[('index.html', context)],
        outpath='reports/_build')
    site.render()
    upload_html()

if __name__ == "__main__":
    cli()
