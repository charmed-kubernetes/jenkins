#!/usr/bin/python3
from launchpadlib.launchpad import Launchpad
import configbag
import click


def reach_lp_builders():
    """Try to login to LP and reach the latest microk8s snap. It will prompt you
    for authorisation if no credentials file is found."""
    # log in
    launchpad = Launchpad.login_with(
        "Launchpad Snap Build Trigger",
        "production",
        configbag.cachedir,
        credentials_file=configbag.creds,
        version="devel",
    )

    # get launchpad team data and ppa
    snappydev = launchpad.people[configbag.people_name]

    launchpad.snaps.getByName(name=configbag.snap_name, owner=snappydev)


if __name__ == "__main__":
    click.echo("Trying to reach microk8s builders")
    reach_lp_builders()
