""" Tracks the progress of a release through it's different stages
"""

import sys
import os

sys.path.insert(0, os.environ["WORKSPACE"])

import argparse
import click
from cilib.service.aws import Store

store = Store("ReleaseTracker")


def parse_options(argv):
    parser = argparse.ArgumentParser(prog="release-tracker")
    parser.add_argument(
        "-d",
        "--debug",
        action="store_true",
        dest="debug",
        default=False,
        help="Enable debug logging.",
    )
    parser.add_argument("--release-id", dest="release_id", help="Release ID of job")

    subparsers = parser.add_subparsers()
    phase = subparsers.add_parser("set-phase")
    phase.add_argument("--name", dest="phase_name")
    phase.add_argument(
        "--result",
        dest="phase_result",
        type=str,
        choices=["pass", "fail", "timeout"],
        help="result of phase",
    )
    phase.set_defaults(func=set_phase)

    g_phase = subparsers.add_parser("get-phase")
    g_phase.add_argument("--name", dest="phase_name")
    g_phase.set_defaults(func=get_phase)

    return parser.parse_args(argv)


def store_results(db):
    """saves the current state of release"""
    store.put_item(Item=dict(db))


def get_phase(db, opts):
    """checks for existing phase and returns result"""
    if db.get(opts.phase_name, "fail") == "fail":
        return click.echo(1)
    return click.echo(0)


def set_phase(db, opts):
    """sets a phase result

    0 for pass, 1 for fail, 2 for timeout
    """
    db[opts.phase_name] = opts.phase_result
    store_results(db)


if __name__ == "__main__":
    db = {}

    opts = parse_options(sys.argv[1:])

    response = store.get_item(Key={"release_id": opts.release_id})
    if response and "Item" in response:
        db = response["Item"]
    else:
        db["release_id"] = opts.release_id

    opts.func(db, opts)
