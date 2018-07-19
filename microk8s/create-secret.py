#!/usr/bin/python3
from launchpadlib.launchpad import Launchpad
import configbag

def reach_lp_builders():
    # log in
    launchpad = Launchpad.login_with('Launchpad Snap Build Trigger',
                                     'production', configbag.cachedir,
                                     credentials_file=configbag.creds,
                                     version='devel')

    # get launchpad team data and ppa
    snappydev = launchpad.people[configbag.people_name]

    launchpad.snaps.getByName(name=configbag.snap_name, owner=snappydev)


if __name__ == '__main__':
    print("Trying to reach microk8s builders")
    reach_lp_builders()
