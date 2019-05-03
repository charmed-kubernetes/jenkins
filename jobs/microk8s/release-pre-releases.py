#!/usr/bin/python3

import os
from configbag import get_tracks
from utils import upstream_release, get_latest_pre_release, compare_releases
from snapstore import Microk8sSnap


# Set this to 'no' if you are sure you want to release
dry_run = os.environ.get('DRY_RUN', 'yes')

# Set this to 'yes' to bypass any check such as new version present.
always_release = os.environ.get('ALWAYS_RELEASE', 'no')

# If you do not specify TRACKS all tracks will be processes
tracks_requested = os.environ.get('TRACKS')
if not tracks_requested or tracks_requested.strip() == '':
    tracks_requested = get_tracks()
else:
    tracks_requested = tracks_requested.split()

# If JUJU_UNIT is not set the tests will be run in local LXC containers
juju_unit = os.environ.get('JUJU_UNIT')
if juju_unit and juju_unit.strip() == '':
    juju_unit = None

juju_controller = os.environ.get('JUJU_CONTROLLER')
if juju_controller and juju_controller.strip() == '':
    juju_controller = None


if __name__ == '__main__':
    '''
    Releases pre-releases to channels in the tracks provided in $TRACKS.
    '''
    print("Check GH for a pre-release and release to the right channel.")
    print("Dry run is set to '{}'.".format(dry_run))
    for track in tracks_requested:
        if track == 'latest':
            print("Skipping latest track")
            continue

        print("Looking at track {}".format(track))
        upstream = upstream_release(track)
        if upstream:
            print("There is already an upstream stable release. We do not release pre-releases.")
            continue

        # Make sure the track is clear from stable releases.
        track_has_stable_release = False
        for channel in ['edge', 'beta', 'candidate', 'stable']:
            snap = Microk8sSnap(track, channel)
            if snap.released and not snap.is_prerelease:
                track_has_stable_release = True
                break

        if track_has_stable_release:
            print("There is already an non-pre-release snap in the store. We do not release pre-releases.")
            continue

        for channel in [('edge', 'alpha'), ('beta', 'beta'), ('candidate', 'rc')]:
            pre_release = get_latest_pre_release(track, channel[1])
            if not pre_release:
                print("No {} pre-release".format(channel[1]))
                continue
            snap = Microk8sSnap(track, channel[0])
            if snap.released and compare_releases(snap.version, pre_release) >= 0 and always_release == 'no':
                print("Nothing to do because snapstore has {} and pre-release is {} and always-release is {}"
                      .format(snap.released, pre_release, always_release))
                continue
            print("Building and releasing {}".format(pre_release))
            snap.build_and_release(pre_release, dry_run)
