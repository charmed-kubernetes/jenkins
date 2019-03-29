""" Tracks the progress of a release through it's different stages
"""

import click
import boto3
from kv import KV

db = KV('tracker.db')
session = boto3.Session(region_name='us-east-1')
dynamodb = session.resource('dynamodb')
table = dynamodb.Table('ReleaseTracker')

@click.group()
def cli():
    pass


@cli.command()
def store_results(release_id):
    """ saves the current state of release
    """
    tracker_db['release_id'] = release_id
    # try to pull existing release id data
    response = table.get_item(
        Key={'release_id': release_id}
    )
    if response and 'Item' in response:
        tracker_db = response['Item']


    table.put_item(Item=dict(tracker_db))

@cli.command()
@click.option('--release-id', required=True, help="release_id of release job")
@click.argument('phase')
def get_phase(release_id, phase):
    """ checks for existing phase and returns result
    """
    response = table.get_item(
        Key={'release_id': release_id}
    )
    if response and 'Item' in response:
        return int(response['Item'][phase])
    return 1

@cli.command()
@click.option('--release-id', required=True, help="release_id of release job")
@click.argument('phase')
@click.argument('result')
def set_phase(release_id, phase, result):
    """ sets a phase result

    0 for pass, 1 for fail, 2 for timeout
    """
    table.put_item(
        Item=dict(db)
    )

if __name__ == "__main__":
    cli()

