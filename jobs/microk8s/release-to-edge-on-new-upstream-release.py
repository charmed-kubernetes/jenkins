#!/usr/bin/python3

import configbag
from snapstore import Microk8sSnap
from launchpadlib.launchpad import Launchpad
from lazr.restfulclient.errors import HTTPError
from configbag import get_tracks
from utils import upstream_release


def trigger_lp_builders(track):
    """Trigger the LP builder of the track provided. This method will
    login using the cached credentials or prompt you for authorization."""
    if track == "latest":
        snap_name = configbag.snap_name
    else:
        snap_name = "{}-{}".format(configbag.snap_name, track)

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
    for track in get_tracks(all=True):
        print("Looking at track {}".format(track))
        upstream = upstream_release(track)
        if not upstream:
            continue
        edge_snap = Microk8sSnap(track, 'edge')
        if not edge_snap.released:
            # Nothing released on edge. LP builders are probably not in place
            continue
        print("Upstream has {} and snapped version is at {}".format(upstream, edge_snap.version))
        if upstream != edge_snap.version:
            if not upstream.startswith("{}.".format(edge_snap.major_minor_version)):
                # There is a minor version difference.
                # For example upstream says we are on v1.12.x and the edge snap is on v1.11.y
                # This should occur only in the "latest" track that follows the latest k8s
                if track != 'latest':
                    print("Track {} has an edge snap of {}.".format(track, edge_snap.version))
                    raise Exception("Tracks should not change releases")

            print("Triggering LP builders")
            request = trigger_lp_builders(track)
            if request:
                print("microk8s is building under: {}".format(request))
