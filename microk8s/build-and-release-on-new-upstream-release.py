#!/usr/bin/python3

import requests
import configbag
import canonicalwebteam.snapstoreapi.public_api as public_api
from launchpadlib.launchpad import Launchpad
from lazr.restfulclient.errors import HTTPError


tracks = ["latest", "1.10", "1.11", "1.12", "1.13", "1.14", "1.15"]


def upstream_release(release):
    """Return the latest stable k8s in the release series"""
    if release == "latest":
        release_url = "https://dl.k8s.io/release/stable.txt"
    else:
        release_url = "https://dl.k8s.io/release/stable-{}.txt".format(release)

    r = requests.get(release_url)
    if r.status_code == 200:
        return r.content.decode().strip()
    else:
        None


def snapped_release(track):
    """ Return the version of the microk8s snap in the edge channel and the track provided"""
    snap_details = public_api.get_snap_details('microk8s', 'edge')
    tracks = snap_details['channel_maps_list']
    channel = "{}/edge".format(track) if track != "latest" else "edge"
    versions = [c['version'] for t in tracks if t['track'] == track
                for c in t['map'] if c['channel'] == channel]
    version = versions[0] if versions else None
    return version


def trigger_lp_builders(track):
    """Trigger the LP builder of the track provided. This method will
    login using the cached credentials or prompt you for authorization."""
    if track == "latest":
        snap_name = "microk8s"
    else:
        snap_name = "microk8s-{}".format(track)

    # log in
    launchpad = Launchpad.login_with('Launchpad Snap Build Trigger',
                                     'production', configbag.cachedir,
                                     credentials_file=configbag.creds,
                                     version='devel')

    # get launchpad team data and ppa
    snappydev = launchpad.people[configbag.people_name]

    try:
        # get snap
        microk8s = launchpad.snaps.getByName(name=snap_name,
                                               owner=snappydev)
    except HTTPError as e:
        print("Cannot trigger build for track {}. ({})".format(track, e.response))
        return None

    # trigger build
    ubuntu = launchpad.distributions["ubuntu"]
    request = microk8s.requestBuilds(archive=ubuntu.main_archive,
                                      pocket='Updates')
    return request


if __name__ == '__main__':
    print("Running a build and release of microk8s")
    for track in tracks:
        print("Looking at track {}".format(track))
        upstream = upstream_release(track)
        if not upstream:
            continue
        snapped = snapped_release(track)
        print("Upstream has {} and snapped version is at {}".format(upstream, snapped))
        if upstream != snapped:
            print("Triggering LP builders")
            request = trigger_lp_builders(track)
            if request:
                print("microk8s is building under: {}".format(request))
