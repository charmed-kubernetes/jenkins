""" Snap utilities
"""

import sh
import re
import operator


def revisions(snap, version_filter=None):
    """ Get revisions of snap

    snap: name of snap
    version_filter: snap version to filter on
    """
    re_comp = re.compile("[ \t+]{2,}")
    revision_list = sh.snapcraft.revisions(snap, _err_to_out=True)
    revision_list = revision_list.stdout.decode().splitlines()[1:]
    revision_parsed = {}
    for line in revision_list:
        rev, uploaded, arch, upstream_version, channels = re_comp.split(line)
        rev = int(rev)
        if version_filter and upstream_version != version_filter:
            continue
        revision_parsed[rev] = {
            "rev": rev,
            "uploaded": uploaded,
            "arch": arch,
            "version": upstream_version,
            "channels": channels,
        }
    return revision_parsed


def latest(snap, version=None):
    """ Get latest snap revision
    """
    return max(revisions(snap, version).items(), key=operator.itemgetter(0))[1]
