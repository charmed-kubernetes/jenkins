import subprocess
import sys

import boto3
from botocore.exceptions import ClientError


session = boto3.Session(profile_name='default', region_name='us-east-1')
dynamodb = session.resource('dynamodb')
table = dynamodb.Table('kubeflow')

head = (
    subprocess.check_output(
        ['git', 'rev-parse', 'HEAD'], cwd='bundle-kubeflow'
    )
    .decode('utf-8')
    .strip()
)

try:
    old_head = table.get_item(Key={'name': 'latest-bundle-commit'})['Item']['value']
except (KeyError, ClientError) as err:
    print(f'Got an error while retrieving old head: {err}', file=sys.stderr)
    old_head = None

print(f'Old HEAD: {old_head}', file=sys.stderr)
print(f'Parsed HEAD: {head}', file=sys.stderr)

if old_head == head:
    print('NO')
else:
    table.put_item(Item={'name': 'latest-bundle-commit', 'value': head})
    print('GO')
