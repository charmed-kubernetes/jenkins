#!/usr/bin/python3

import os
from .snapstore import Microk8sSnap
from .configbag import tracks


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
    tracks_requested = tracks
else:
    tracks_requested = tracks_requested.split()


if __name__ == '__main__':
    '''
    Releases to beta and candidate what is under edge on the tracks provided in $TRACKS.
    Cross distro tests should run.
    '''
    print("Check edge for a new release cross-distro test and release to beta and candidate.")
    print("Dry run is set to '{}'.".format(dry_run))
    for track in tracks_requested:
        print("Looking at track {}".format(track))
        edge_snap = Microk8sSnap(track, 'edge')
        if not edge_snap.released:
            print("Nothing released on {} edge.".format(track))
            break

        beta_snap = Microk8sSnap(track, 'beta')
        if beta_snap.released:
            # We already have a snap on beta. Let's see if we have to push a new release.
            if beta_snap.version == edge_snap.version and always_release == 'no':
                # Beta and edge are the same version. Nothing to release on this track.
                print("Beta and edge have the same version {}. We will not release.".format(beta_snap.version))
                continue

            print("Beta is at {}, edge at {}, and 'always_release' is {}.".format(
                beta_snap.version, edge_snap.version, always_release
            ))
            edge_snap.test_cross_distro(channel_to_upgrade='beta', tests_branch=tests_branch)
        else:
            print("Beta channel is empty. Releasing without any testing.")

        # The following will raise exceptions in case of a failure
        edge_snap.release_to('beta', dry_run=dry_run)
        edge_snap.release_to('candidate', dry_run=dry_run)
