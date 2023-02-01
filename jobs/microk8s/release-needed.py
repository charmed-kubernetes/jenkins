#!/usr/bin/python3

# This script checks if there is a potential release to channel $CHANNEL.
# It is meant to be called from Jenkins but you can call it from your host yourself, eg
# CHANNEL=beta python3 ./release-needed.py
#
# Returns:
#  - 0: if a release is needed
#  - 1: if no release is needed


import os
import click
from datetime import datetime, timezone
from snapstore import Microk8sSnap
from configbag import get_tracks
from utils import upstream_release, get_source_track_channel


# Set this to 'yes' to bypass any check such as new version present.
always_release = os.environ.get("ALWAYS_RELEASE", "no")

# If you do not specify TRACKS all tracks will be processed
tracks_requested = os.environ.get("TRACKS")
if not tracks_requested or tracks_requested.strip() == "":
    tracks_requested = get_tracks()
else:
    tracks_requested = tracks_requested.split()

channel = os.environ.get("CHANNEL", "beta")

if __name__ == "__main__":
    """
    Check if we need to release to the input channel what is under candidate on the tracks provided in $TRACKS.
    """
    click.echo("Check if we are to release to {}.".format(channel))

    if channel not in ["stable", "candidate", "beta"]:
        click.echo(
            "Cannot pre-check for release channel {}. Going forward with the release.".format(
                channel
            )
        )
        exit(0)

    if always_release == "yes":
        exit(0)

    for track in tracks_requested:
        upstream = upstream_release(track)
        if not upstream:
            click.echo("No upstream release yet.")
            continue

        source_track, source_channel = get_source_track_channel(
            track, channel, upstream
        )
        click.echo(
            "Track {}/{} the {}/{}".format(track, channel, source_track, source_channel)
        )
        source_snap = Microk8sSnap(source_track, source_channel)

        if not source_snap.released:
            # Nothing to release
            click.echo(
                "Nothing on {}/{}. Nothing to release.".format(
                    source_track, source_channel
                )
            )
            break

        if (
            datetime.now(timezone.utc) - source_snap.release_date
        ).days < 8 and channel == "stable":
            # Candidate not mature enough
            click.echo(
                "Nothing to release because candidate is {} days old".format(
                    (datetime.now(timezone.utc) - source_snap.release_date).days,
                )
            )
            continue

        target_snap = Microk8sSnap(track, channel)
        if target_snap.released and not target_snap.is_prerelease:
            # We already have a snap released that is not a pre-release. Lets run some tests.
            if source_snap.version == target_snap.version:
                # Source and target have the same version. Nothing to release.
                click.echo(
                    "{}/{} and {}/{} have the same version {}. We will not release.".format(
                        track,
                        channel,
                        source_track,
                        source_channel,
                        target_snap.version,
                    )
                )
                continue

        # We need to do a release
        click.echo(
            "We need to try to release to {} on track {}.".format(channel, track)
        )
        exit(0)

    # We went through all tracks and we did not find anything to release
    exit(1)
