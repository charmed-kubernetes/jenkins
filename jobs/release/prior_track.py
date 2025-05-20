#!/usr/bin/env python

"""Given a release track, calculate the prior release track.

| step  | input           | output |
| ---   | ---             | ---    |
| 0     | 1.32/candidate  | 1.32   |
| 1     | 1.32/edge       | 1.31   |
| 2     | 1.32/beta       | 1.30   |
"""

import argparse


parser = argparse.ArgumentParser(description="Release steps calculator")
parser.add_argument(
    "channel",
    type=str,
    help="Release channel in the format <track>/<risk>",
)
parser.add_argument(
    "step",
    type=int,
    help="Release step",
)

args = parser.parse_args()
channel = args.channel.split("/")
if len(channel) != 2:
    raise ValueError("Invalid channel format. Expected <track>/<risk>.")

track = channel[0].split(".")
if len(track) != 2:
    raise ValueError("Invalid track format. Expected <major>.<minor>.")

minor = int(track[1])
print(f"{track[0]}.{minor - args.step}")
