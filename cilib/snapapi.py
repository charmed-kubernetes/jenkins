import sh
import re
import semver
import json
from cilib.run import capture
from functools import cached_property


class SnapStore:
    def __init__(self, snap):
        self.snap = snap
        self.creds = "production-creds"
        self.api = f"https://dashboard.snapcraft.io/api/v2/snaps/{snap}"

    @cached_property
    def channel_map(self):
        """Gets the channel map for a snap"""
        output = capture(
            ["surl_cli.py", "-a", self.creds, "-X", "GET", f"{self.api}/channel-map"]
        ).stdout.decode()
        return json.loads(output)

    def max_rev(self, arch, track):
        """Returns max revision for snap by arch/track"""
        if "channel-map" not in self.channel_map:
            print(f"Invalid channel map: {self.channel_map}")
        for channel in self.channel_map["channel-map"]:
            if channel["channel"] == track and channel["architecture"] == arch:
                return int(channel["revision"])
        return None

    def version_from_rev(self, revision, arch):
        """Returns the version associated with revision and architecture of snap"""
        for channel in self.channel_map["revisions"]:
            if arch in channel["architectures"] and revision == channel["revision"]:
                return semver.VersionInfo.parse(channel["version"])
        return None


def max_rev(revlist, version_filter):
    return max(
        [
            int(sublist[0])
            for sublist in revlist
            if sublist[-2].startswith(version_filter)
        ]
    )


def all_published(snap):
    """Get all known published snap versions, tracks, arch"""
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
    """Get revisions of snap

    snap: name of snap
    version_filter: snap version to filter on
    """

    re_comp = re.compile("[ \t+]{2,}")
    revision_list = sh.snapcraft.revisions(snap, "--arch", arch, _err_to_out=True)
    revision_list = revision_list.stdout.decode().splitlines()[1:]

    revisions_to_process = []
    for line in revision_list:
        line = re_comp.split(line)
        try:
            semver.parse(line[-2])
            revisions_to_process.append(line)
        except ValueError:
            print(f"Skipping: {line}")
            continue

    revision_list = [
        line
        for line in revisions_to_process
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
    """Get latest snap revision"""
    return revisions(snap, version_track, arch, exclude_pre)
