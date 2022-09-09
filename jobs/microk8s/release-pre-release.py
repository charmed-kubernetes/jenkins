#!/usr/bin/python3

import os
import click
from configbag import get_tracks
from utils import upstream_release, get_latest_pre_release, compare_releases
from snapstore import Microk8sSnap


# Set this to 'no' if you are sure you want to release
dry_run = os.environ.get("DRY_RUN", "yes")

# Set this to 'yes' to bypass any check such as new version present.
always_release = os.environ.get("ALWAYS_RELEASE", "no")

# If you do not specify TRACKS all tracks will be processes
tracks_requested = os.environ.get("TRACKS")
if not tracks_requested or tracks_requested.strip() == "":
    tracks_requested = get_tracks()
else:
    tracks_requested = tracks_requested.split()

# If JUJU_UNIT is not set the tests will be run in local LXC containers
juju_unit = os.environ.get("JUJU_UNIT")
if juju_unit and juju_unit.strip() == "":
    juju_unit = None

juju_controller = os.environ.get("JUJU_CONTROLLER")
if juju_controller and juju_controller.strip() == "":
    juju_controller = None

juju_model = os.environ.get("JUJU_MODEL")
if juju_model and juju_model.strip() == "":
    juju_model = None


if __name__ == "__main__":
    """
    Releases pre-releases to channels in the tracks provided in $TRACKS.
    """
    click.echo("Check GH for a pre-release and release to the right channel.")
    click.echo("Dry run is set to '{}'.".format(dry_run))
    for track in tracks_requested:
        if track == "latest":
            click.echo("Skipping latest track")
            continue

        if track.endswith("-eksd"):
            click.echo("We do not release pre-releases for EKS-D.")
            continue

        click.echo("Looking at track {}".format(track))
        upstream = upstream_release(track)
        if upstream:
            click.echo(
                "There is already an upstream stable release. We do not release pre-releases."
            )
            continue

        # Make sure the track is clear from stable releases.
        track_has_stable_release = False
        for channel in ["edge", "beta", "candidate", "stable"]:
            snap = Microk8sSnap(track, channel)
            if snap.released and not snap.is_prerelease:
                track_has_stable_release = True
                break

        if track_has_stable_release:
            click.echo(
                "There is already an non-pre-release snap in the store. We do not release pre-releases."
            )
            continue

        for channel in [("candidate", "rc"), ("beta", "beta"), ("edge", "alpha")]:
            pre_release = get_latest_pre_release(track, channel[1])
            if not pre_release:
                click.echo("No {} pre-release".format(channel[1]))
                continue
            snap = Microk8sSnap(
                track,
                channel[0],
                juju_unit=juju_unit,
                juju_controller=juju_controller,
                juju_model=juju_model,
            )
            if (
                snap.released
                and compare_releases(snap.version, pre_release) >= 0
                and always_release == "no"
            ):
                click.echo(
                    "Nothing to do because snapstore has {} and pre-release is {} and always-release is {}".format(
                        snap.released, pre_release, always_release
                    )
                )
                continue
            click.echo("Building and releasing {}".format(pre_release))
            snap.build_and_release(pre_release, dry_run)
            # We only build the last pre-release
            break
