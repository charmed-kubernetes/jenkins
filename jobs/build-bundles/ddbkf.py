"""Checks if latest commit to bundle-kubeflow has changed.

Uses DDB to store latest commit
"""
import subprocess
import sys

import boto3
from botocore.exceptions import ClientError


def get_table():
    session = boto3.Session(profile_name='default', region_name='us-east-1')
    dynamodb = session.resource('dynamodb')
    return dynamodb.Table('kubeflow')


def get_head():
    return (
        subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd='bundle-kubeflow')
        .decode('utf-8')
        .strip()
    )


def go_or_no():
    """Checks whether or not the release should proceed."""

    table = get_table()
    head = get_head()

    try:
        old_head = table.get_item(Key={'name': 'latest-bundle-commit'})['Item']['value']
    except (KeyError, ClientError) as err:
        print(f'Got an error while retrieving old head: {err}', file=sys.stderr)
        old_head = None

    print(f'Old HEAD: {old_head}', file=sys.stderr)
    print(f'Parsed HEAD: {head}', file=sys.stderr)

    if old_head == head:
        return 'NO'
    else:
        return 'GO'


def update_ddb():
    """Updates DDB with most recent HEAD after successful run."""

    get_table().put_item(Item={'name': 'latest-bundle-commit', 'value': get_head()})


if __name__ == '__main__':
    if sys.argv[1] == 'check':
        print(go_or_no())
    elif sys.argv[1] == 'update':
        update_ddb()
    else:
        print(f'`{sys.argv[1]}` not understood!')
