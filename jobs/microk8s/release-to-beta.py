#!/usr/bin/python3

import os
from snapstore import Microk8sSnap
from configbag import get_tracks
from utils import upstream_release


# Set this to 'no' if you are sure you want to release
dry_run = os.environ.get('DRY_RUN', 'yes')

# Set this to 'yes' to bypass any check such as new version present.
always_release = os.environ.get('ALWAYS_RELEASE', 'no')

# If TESTS_BRANCH is not set the tests branch will be the one matching the track
tests_branch = os.environ.get('TESTS_BRANCH')
if tests_branch and tests_branch.strip() == '':
    tests_branch = None

# If you do not specify TRACKS all tracks will be processes
tracks_requested = os.environ.get('TRACKS')
if not tracks_requested or tracks_requested.strip() == '':
    tracks_requested = get_tracks()
else:
    tracks_requested = tracks_requested.split()

# Set this to the proxy your environment may have
proxy = os.environ.get('PROXY')
if not proxy or proxy.strip() == '':
    proxy = None

# If JUJU_UNIT is not set the tests will be run in local LXC containers
juju_unit = os.environ.get('JUJU_UNIT')
if juju_unit and juju_unit.strip() == '':
    juju_unit = None

juju_controller = os.environ.get('JUJU_CONTROLLER')
if juju_controller and juju_controller.strip() == '':
    juju_controller = None


if __name__ == '__main__':
    '''
    Releases to beta and candidate what is under edge on the tracks provided in $TRACKS.
    Cross distro tests should run.
    '''
    print("Check edge for a new release cross-distro test and release to beta and candidate.")
    print("Dry run is set to '{}'.".format(dry_run))
    for track in tracks_requested:
        print("Looking at track {}".format(track))
        upstream = upstream_release(track)
        if not upstream:
            print("No stable upstream release yet.")
            continue
        edge_snap = Microk8sSnap(track, 'edge', juju_unit, juju_controller)
        if not edge_snap.released:
            print("Nothing released on {} edge.".format(track))
            break

        beta_snap = Microk8sSnap(track, 'beta', juju_unit, juju_controller)
        if beta_snap.released and not beta_snap.is_prerelease:
            # We already have a snap on beta that is not a pre-release. Let's see if we have to push a new release.
            if beta_snap.version == edge_snap.version and always_release == 'no':
                # Beta and edge are the same version. Nothing to release on this track.
                print("Beta and edge have the same version {}. We will not release.".format(beta_snap.version))
                continue

            print("Beta is at {}, edge at {}, and 'always_release' is {}.".format(
                beta_snap.version, edge_snap.version, always_release
            ))
            edge_snap.test_cross_distro(channel_to_upgrade='beta',
                                        tests_branch=tests_branch,
                                        proxy=proxy)
        else:
            if not beta_snap.released:
                print("Beta channel is empty. Releasing without any testing.")
            elif beta_snap.is_prerelease:
                print("Beta channel holds a prerelease. Releasing without any testing.")
            else:
                print("Beta channel holds a release that is not a prerelease. We should be testing that.")
                assert False

        # The following will raise exceptions in case of a failure
        edge_snap.release_to('beta', dry_run=dry_run)
        edge_snap.release_to('candidate', dry_run=dry_run)
