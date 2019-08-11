import sh
import re
import operator
import semver
from pprint import pformat


def max_rev(revlist, version_filter):
    return max([int(sublist[0])
                for sublist in revlist
                if sublist[-2].startswith(version_filter)
    ])

def revisions(snap, version_filter, arch="amd64", exclude_pre=False):
    """ Get revisions of snap

    snap: name of snap
    version_filter: snap version to filter on
    """

    re_comp = re.compile("[ \t+]{2,}")
    revision_list = sh.snapcraft.revisions(snap, "--arch", arch, _err_to_out=True)
    revision_list = revision_list.stdout.decode().splitlines()[1:]
    revision_parsed = {}
    revision_list = [
        re_comp.split(line)
        for line in revision_list
    ]
    revision_list = [
        line
        for line in revision_list
        if exclude_pre and semver.parse(line[-2])['prerelease'] is None
    ]
    rev = max_rev(revision_list, version_filter)
    rev_map = [
        line for line in revision_list if rev == int(line[0])
    ]

    if rev_map:
        return rev_map[0]
    return []


def latest(snap, version, arch="amd64", exclude_pre=False):
    """ Get latest snap revision
    """
    return revisions(snap, version, arch, exclude_pre)
