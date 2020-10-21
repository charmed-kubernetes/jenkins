""" Repo classes for downstream snaps """

from . import BaseRepoModel
from cilib import enums, log
import os
import sh
import re
import semver


class SnapBaseRepoModel:
    name = None

    def __init__(self):
        self.version = None
        self.git_user = "k8s-team-ci"
        self.repo = f"git+ssh://{self.git_user}@git.launchpad.net/snap-{self.name}"
        self.src = f"snap-{self.name}"

    def __str__(self):
        return f"<{self.name}>"

    def debug(self, msg):
        log.debug(f"[{self.name}] {msg}")

    @property
    def base(self):
        return BaseRepoModel(repo=self.repo, git_user=self.git_user, name=self.name)

    @property
    def tracks(self):
        """Tracks to publish a snap to"""
        return enums.SNAP_K8S_TRACK_MAP[self.version]

    def revisions(self, arch="amd64", exclude_pre=False):
        """Grab revision data

        TODO: rework to query all arches in one go and update data structure
        {rev: {arch: {**items}}
        """
        re_comp = re.compile("[ \t+]{2,}")
        revision_list = self._get_revision_output(arch)

        revision_map = {}
        for line in revision_list:
            rev, timestamp, arch, version, channels = re_comp.split(line)
            channels = [
                {
                    "promoted": channel.endswith("*"),
                    "channel": channel.rstrip("*").strip(),
                }
                for channel in channels.split(",")
            ]
            try:
                version = semver.VersionInfo.parse(version)
            except ValueError:
                print(f"Skipping invalid semver: {line}")
                continue

            if exclude_pre and version.prerelease is not None:
                continue

            revision_map[rev] = {
                "timestamp": timestamp,
                "arch": arch,
                "version": version,
                "channels": channels,
            }
        return revision_map

    def latest_revision(self, track, arch="amd64", exclude_pre=False):
        """Get latest revision of snap based on track and arch"""

        _revisions_map = self.revisions(arch)
        _revisions_list = []

        for rev in _revisions_map.keys():
            if exclude_pre and _revisions_map[rev]["version"].prerelease is not None:
                continue

            for channel in _revisions_map[rev]["channels"]:
                if not channel["promoted"]:
                    continue
                if track == channel["channel"]:
                    _revisions_list.append(int(rev))
        return max(_revisions_list)

    # private
    def _get_revision_output(self, arch):
        revision_list = sh.snapcraft.revisions(
            self.name, "--arch", arch, _err_to_out=True
        )
        return revision_list.stdout.decode().splitlines()[1:]


class SnapKubeApiServerRepoModel(SnapBaseRepoModel):
    def __init__(self):
        self.name = "kube-apiserver"
        super(SnapKubeApiServerRepoModel, self).__init__()


class SnapKubeControllerManagerRepoModel(SnapBaseRepoModel):
    def __init__(self):
        self.name = "kube-controller-manager"
        super(SnapKubeControllerManagerRepoModel, self).__init__()


class SnapKubeProxyRepoModel(SnapBaseRepoModel):
    def __init__(self):
        self.name = "kube-proxy"
        super(SnapKubeProxyRepoModel, self).__init__()


class SnapKubeSchedulerRepoModel(SnapBaseRepoModel):
    def __init__(self):
        self.name = "kube-scheduler"
        super(SnapKubeSchedulerRepoModel, self).__init__()


class SnapKubectlRepoModel(SnapBaseRepoModel):
    def __init__(self):
        self.name = "kubectl"
        super(SnapKubectlRepoModel, self).__init__()


class SnapKubeadmRepoModel(SnapBaseRepoModel):
    def __init__(self):
        self.name = "kubeadm"
        super(SnapKubeadmRepoModel, self).__init__()


class SnapKubeletRepoModel(SnapBaseRepoModel):
    def __init__(self):
        self.name = "kubelet"
        super(SnapKubeletRepoModel, self).__init__()


class SnapKubernetesTestRepoModel(SnapBaseRepoModel):
    def __init__(self):
        self.name = "kubernetes-test"
        super(SnapKubernetesTestRepoModel, self).__init__()
