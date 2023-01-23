#!/usr/bin/python3

# This script checks if there is a potential release of the beta channel to stable.
# It is meant to be called from Jenkins but you can call it from your host yourself, eg
# ALWAYS_RELEASE=yes python3 ./release-needed-to-stable.py
#
# Returns:
#  - 0: if a release is needed
#  - 1: if no release is needed


import os
import click
from datetime import datetime, timezone
from snapstore import Microk8sSnap
from configbag import get_tracks
from utils import upstream_release


# Set this to 'yes' to bypass any check such as new version present.
always_release = os.environ.get("ALWAYS_RELEASE", "no")

# If you do not specify TRACKS all tracks will be processed
tracks_requested = os.environ.get("TRACKS")
if not tracks_requested or tracks_requested.strip() == "":
    tracks_requested = get_tracks()
else:
    tracks_requested = tracks_requested.split()


if __name__ == "__main__":
    """
    Check if we need to release to stable what is under candidate on the tracks provided in $TRACKS.
    """
    click.echo("Check candidate maturity and check if we are to release to stable.")
    if always_release == "yes":
        exit(0)

    for track in tracks_requested:

        upstream = upstream_release(track)
        if not upstream:
            click.echo("No stable upstream release yet.")
            continue

        if track == "latest":
            ersion = upstream[1:]
            ersion_list = ersion.split(".")
            source_track = "{}.{}".format(ersion_list[0], ersion_list[1])
            source_channel = "stable"
            click.echo(
                "latest/stable is populated from the {}/{}".format(
                    source_track, source_channel
                )
            )
        else:
            source_track = track
            source_channel = "candidate"
            click.echo(
                "{}/stable is populated from the {}/{}".format(
                    track, source_track, source_channel
                )
            )

        candidate_snap = Microk8sSnap(source_track, source_channel)
        if not candidate_snap.released:
            # Nothing to release
            click.echo("Nothing on candidate. Nothing to release.")
            break

        if (
            datetime.now(timezone.utc) - candidate_snap.release_date
        ).days < 8 and always_release == "no":
            # Candidate not mature enough
            click.echo(
                "Nothing to release because candidate is {} days old".format(
                    (datetime.now(timezone.utc) - candidate_snap.release_date).days,
                )
            )
            continue

        stable_snap = Microk8sSnap(track, "stable")
        if stable_snap.released and not stable_snap.is_prerelease:
            # We already have a snap released on stable that is not a pre-release. Lets run some tests.
            if candidate_snap.version == stable_snap.version and always_release == "no":
                # Candidate and stable are the same version. Nothing to release.
                click.echo(
                    "Stable and candidate have the same version {}. We will not release.".format(
                        stable_snap.version
                    )
                )
                continue
        
        # We need to do a release
        click.echo(
            "We need to try to release to stable on track {}.".format(track)
        )
        exit(0)
    
    # We went through all tracks and we did not find anything to release
    exit(1)
