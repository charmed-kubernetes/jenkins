""" Repo classes for downstream snaps """

from . import BaseRepoModel
from pymacaroons import Macaroon
from cilib import lp, idm, enums
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

    @property
    def base(self):
        return BaseRepoModel(repo=self.repo, git_user=self.git_user, name=self.name)

    @property
    def tracks(self):
        """Tracks to publish a snap to"""
        return enums.SNAP_K8S_TRACK_MAP[self.version]

    def revisions(self, arch="amd64", exclude_pre=False):
        """Grab revision data"""
        re_comp = re.compile("[ \t+]{2,}")
        revision_list = self._get_revision_output(arch)

        revision_map = {}
        for line in revision_list:
            rev, timestamp, arch, version, channels = re_comp.split(line)
            channels = [
                {"promoted": channel.endswith("*"), "channel": channel.rstrip("*")}
                for channel in channels.split(",")
            ]
            try:
                semver.parse(version)
            except ValueError:
                print(f"Skipping invalid semver: {line}")
                continue
            revision_map[rev] = {
                "timestamp": timestamp,
                "arch": arch,
                "string_version": version,
                "version": semver.parse(version),
                "channels": channels,
            }
        return revision_map

    def latest_revision(self, track, arch="amd64", exclude_pre=False):
        """Get latest revision of snap based on track and arch"""

        _revisions_map = self.revisions(arch)
        _revisions_list = []

        for rev in _revisions_map.keys():
            for channel in _revisions_map[rev]["channels"]:
                if not channel["promoted"]:
                    continue
                if track != channel["channel"]:
                    continue
            if exclude_pre and _revisions_map[rev]["version"]["prerelease"] is not None:
                continue
            _revisions_list.append(rev)

        return max(_revisions_list)

    def create_recipe(self, branch):
        """ Creates an new snap recipe in Launchpad

        tag: launchpad git tag to pull snapcraft instructions from (ie, git.launchpad.net/snap-kubectl)

        # Note: this account would need access granted to the snaps it want's to publish from the snapstore dashboard
        snap_recipe_email: snapstore email for being able to publish snap recipe from launchpad to snap store
        snap_recipe_password: snapstore password for account being able to publish snap recipe from launchpad to snap store

        Usage:

        snap.py create-snap-recipe --snap kubectl --version 1.13 --tag v1.13.2 \
          --track 1.13/edge/hotfix-LP123456 \
          --repo git+ssh://$LPCREDS@git.launchpad.net/snap-kubectl \
          --owner k8s-jenkaas-admins \
          --snap-recipe-email myuser@email.com \
          --snap-recipe-password aabbccddee

        """
        snap_recipe_email = os.environ.get("K8STEAMCI_USR")
        snap_recipe_password = os.environ.get("K8STEAMCI_PSW")

        _client = lp.Client(stage="production")
        _client.login()

        params = {
            "name": self.name,
            "owner": "k8s-jenkaas-admin",
            "version": self.version,
            "branch": branch,
            "repo": self.repo,
            "track": self.tracks,
        }

        click.echo(f"  > creating recipe for {params}")
        snap_recipe = _client.create_or_update_snap_recipe(**params)
        caveat_id = snap_recipe.beginAuthorization()
        cip = idm.CanonicalIdentityProvider(
            email=snap_recipe_email, password=snap_recipe_password
        )
        discharge_macaroon = cip.get_discharge(caveat_id).json()
        discharge_macaroon = Macaroon.deserialize(
            discharge_macaroon["discharge_macaroon"]
        )
        snap_recipe.completeAuthorization(
            discharge_macaroon=discharge_macaroon.serialize()
        )
        snap_recipe.requestBuilds(archive=_client.archive(), pocket="Updates")

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
