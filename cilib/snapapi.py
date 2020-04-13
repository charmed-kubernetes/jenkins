import sh
import re
import operator
import semver
from pprint import pprint, pformat
from cilib.run import capture


def max_rev(revlist, version_filter):
    return max(
        [
            int(sublist[0])
            for sublist in revlist
            if sublist[-2].startswith(version_filter)
        ]
    )


def all_published(snap):
    """ Get all known published snap versions, tracks, arch
    """
    re_comp = re.compile("[ \t+]{2,}")
    revision_list = capture(["snapcraft", "revisions", snap])
    revision_list = revision_list.stdout.decode().splitlines()[1:]
    revision_list = [re_comp.split(line) for line in revision_list]
    publish_map = {"arm64": {}, "ppc64el": {}, "amd64": {}, "s390x": {}}
    for line in revision_list:
        rev, uploaded, arch, version, channels = line
        channels = channels.split(",")
        for chan in channels:
            if chan.endswith("*") and version in publish_map[arch]:
                publish_map[arch][version].append(chan)
            elif chan.endswith("*"):
                publish_map[arch][version] = [chan]
    return publish_map


def revisions(snap, version_filter_track, arch="amd64", exclude_pre=False):
    """ Get revisions of snap

    snap: name of snap
    version_filter: snap version to filter on
    """

    re_comp = re.compile("[ \t+]{2,}")
    revision_list = sh.snapcraft.revisions(snap, "--arch", arch, _err_to_out=True)
    revision_list = revision_list.stdout.decode().splitlines()[1:]
    revision_parsed = {}
    revision_list = [re_comp.split(line) for line in revision_list]
    revision_list = [
        line
        for line in revision_list
        if exclude_pre
        and semver.parse(line[-2])["prerelease"] is None
        and any(version_filter_track in item for item in line)
    ]
    rev = max_rev(revision_list, version_filter_track.split("/")[0])
    rev_map = [line for line in revision_list if rev == int(line[0])]

    if rev_map:
        return rev_map[0]
    return []


def latest(snap, version_track, arch="amd64", exclude_pre=False):
    """ Get latest snap revision
    """
    return revisions(snap, version_track, arch, exclude_pre)
