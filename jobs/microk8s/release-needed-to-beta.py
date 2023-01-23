#!/usr/bin/python3

# This script checks if there is a potential release of the edge channel to beta/candidate.
# It is meant to be called from Jenkins but you can call it from your host yourself, eg
# ALWAYS_RELEASE=yes python3 ./release-needed-to-beta.py
#
# Returns:
#  - 0: if a release is needed
#  - 1: if no release is needed

import os
import click
from snapstore import Microk8sSnap
from configbag import get_tracks
from utils import upstream_release


# Set this to 'yes' to bypass any check such as new version present.
always_release = os.environ.get("ALWAYS_RELEASE", "no")

# If you do not specify TRACKS all tracks will be processes
tracks_requested = os.environ.get("TRACKS")
if not tracks_requested or tracks_requested.strip() == "":
    tracks_requested = get_tracks()
else:
    tracks_requested = tracks_requested.split()

if __name__ == "__main__":
    """
    Check if we are to release to beta and candidate what is under edge on the tracks provided in $TRACKS.
    """
    click.echo("Look into edge for a new release and check if a release is needed.")
    if always_release == "yes":
        exit(0)

    for track in tracks_requested:
        click.echo("Inspecting track {}".format(track))
        upstream = upstream_release(track)
        if not upstream:
            click.echo("No stable upstream release yet.")
            continue
        edge_snap = Microk8sSnap(track, "edge")
        if not edge_snap.released:
            click.echo("Nothing released on {} edge.".format(track))
            # We reached the end of the tracks with edge releases. End the tracks inspection
            break

        beta_snap = Microk8sSnap(track, "beta")
        if beta_snap.released and not beta_snap.is_prerelease:
            # We already have a snap on beta that is not a pre-release. Let's see if we have to push a new release.
            if beta_snap.version == edge_snap.version:
                # Beta and edge are the same version. Nothing to release on this track.
                click.echo(
                    "Beta and edge have the same version {}. We will not release.".format(
                        beta_snap.version
                    )
                )
                continue

        # We need to do a release
        click.echo(
            "We need to try to release to beta on track {}.".format(track)
        )

        exit(0)
    
    # We went through all tracks and we did not find anything to release
    exit(1)
