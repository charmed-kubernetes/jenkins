""" Repo classes for downstream snaps """

from . import BaseRepoModel
from pymacaroons import Macaroon
from cilib import lp, idm, enums
import os
import sh
import re
import semver


class SnapBaseRepoModel():
    def __init__(self):
        self.name = None
        self.version = None
        self.git_user = "k8s-team-ci"
        self.repo = f"git+ssh://{self.git_user}@git.launchpad.net/snap-{self.name}"
        self.repo_model = BaseRepoModel(repo=self.repo, git_user=self.git_user, name=self.name)

    @property
    def tracks(self):
        """Tracks to publish a snap to"""
        return enums.SNAP_K8S_TRACK_MAP[self.version]

    def revisions(version_filter_track, arch="amd64", exclude_pre=False):
        """Get revisions of snap

        snap: name of snap
        version_filter: snap version to filter on
        """

        re_comp = re.compile("[ \t+]{2,}")
        revision_list = sh.snapcraft.revisions(self.name, "--arch", arch, _err_to_out=True)
        revision_list = revision_list.stdout.decode().splitlines()[1:]
        revision_parsed = {}

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
        rev = self.__max_rev(revision_list, version_filter_track.split("/")[0])
        rev_map = [line for line in revision_list if rev == int(line[0])]

        if rev_map:
            return rev_map[0]
        return []

    def latest_revision(self, version_track, arch="amd64", exclude_pre=False):
        """Get latest snap revision"""
        return self.revisions(version_track, arch, exclude_pre)

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
    def __max_rev(revlist, version_filter):
        return max(
            [
                int(sublist[0])
                for sublist in revlist
                if sublist[-2].startswith(version_filter)
            ]
        )


class SnapKubeApiServerRepoModel(SnapBaseRepoModel):
    def __init__(self):
        self.name = "kube-apiserver"
        super().__init__()

class SnapKubeControllerManagerRepoModel(SnapBaseRepoModel):
    def __init__(self):
        self.name = "kube-controller-manager"
        super().__init__()

class SnapKubeProxyRepoModel(SnapBaseRepoModel):
    def __init__(self):
        self.name = "kube-proxy"
        super().__init__()


class SnapKubeSchedulerRepoModel(SnapBaseRepoModel):
    def __init__(self):
        self.name = "kube-scheduler"
        super().__init__()

class SnapKubectlRepoModel(SnapBaseRepoModel):
    def __init__(self):
        self.name = "kubectl"
        super().__init__()


class SnapKubeadmRepoModel(SnapBaseRepoModel):
    def __init__(self):
        self.name = "kubeadm"
        super().__init__()


class SnapKubeletRepoModel(SnapBaseRepoModel):
    def __init__(self):
        self.name = "kubelet"
        super().__init__()


class SnapKubernetesTestRepoModel(SnapBaseRepoModel):
    def __init__(self):
        self.name = "kubernetes-test"
        super().__init__()
