#!/usr/bin/python3

import os
import click
from datetime import datetime, timezone
from snapstore import Microk8sSnap
from configbag import get_tracks
from utils import upstream_release


# Set this to 'no' if you are sure you want to release
dry_run = os.environ.get("DRY_RUN", "yes")

# Set this to 'yes' to bypass any check such as new version present.
always_release = os.environ.get("ALWAYS_RELEASE", "no")

# If TESTS_BRANCH is not set the tests branch will be the one matching the track
tests_branch = os.environ.get("TESTS_BRANCH")
if tests_branch and tests_branch.strip() == "":
    tests_branch = None

# If you do not specify TRACKS all tracks will be processes
tracks_requested = os.environ.get("TRACKS")
if not tracks_requested or tracks_requested.strip() == "":
    tracks_requested = get_tracks()
else:
    tracks_requested = tracks_requested.split()

# Set this to the proxy your environment may have
proxy = os.environ.get("PROXY")
if not proxy or proxy.strip() == "":
    proxy = None

# If JUJU_UNIT is not set the tests will be run in local LXC containers
juju_unit = os.environ.get("JUJU_UNIT")
if juju_unit and juju_unit.strip() == "":
    juju_unit = None

juju_controller = os.environ.get("JUJU_CONTROLLER")
if juju_controller and juju_controller.strip() == "":
    juju_controller = None


if __name__ == "__main__":
    """
    Releases to stable what is under candidate on the tracks provided in $TRACKS.
    Cross distro tests should run.
    """
    click.echo("Check candidate maturity and release microk8s to stable.")
    click.echo("Dry run is set to '{}'.".format(dry_run))
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

        candidate_snap = Microk8sSnap(
            source_track, source_channel, juju_unit, juju_controller
        )
        if not candidate_snap.released:
            # Nothing to release
            click.echo("Nothing on candidate. Nothing to release.")
            break

        if (
            datetime.now(timezone.utc) - candidate_snap.release_date
        ).days < 8 and always_release == "no":
            # Candidate not mature enough
            click.echo(
                "Not releasing because candidate is {} days old and 'always_release' is {}".format(
                    (datetime.now(timezone.utc) - candidate_snap.release_date).days,
                    always_release,
                )
            )
            continue

        stable_snap = Microk8sSnap(track, "stable", juju_unit, juju_controller)
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

            click.echo(
                "Candidate is at {}, stable at {}, and 'always_release' is {}.".format(
                    candidate_snap.version, stable_snap.version, always_release
                )
            )
            candidate_snap.test_cross_distro(
                track_to_upgrade=track,
                channel_to_upgrade="stable",
                tests_branch=tests_branch,
                proxy=proxy,
            )
        else:
            if not stable_snap.released:
                click.echo("Stable channel is empty. Releasing without any testing.")
            elif stable_snap.is_prerelease:
                click.echo(
                    "Stable channel holds a prerelease. Releasing without any testing."
                )
            else:
                click.echo(
                    "Stable channel holds a release that is not a prerelease. We should be testing that."
                )
                assert False

        # The following will raise an exception if it fails
        candidate_snap.release_to("stable", release_to_track=track, dry_run=dry_run)
