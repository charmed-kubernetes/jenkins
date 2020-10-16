""" Repo classes for downstream snaps """

from . import BaseRepoModel
from pymacaroons import Macaroon
from cilib import lp, idm, enums
import os


class SnapBaseRepoModel(BaseRepoModel):
    def create_recipe(self, version, branch, tracks=None):
        """ Creates an new snap recipe in Launchpad

        version: snap version channel apply this too (ie, Current patch is 1.13.3 but we want that to go in 1.13 snap channel)
        track: snap store version/risk/branch to publish to (ie, 1.13/edge/hotfix-LP123456)
        owner: launchpad owner of the snap recipe (ie, k8s-jenkaas-admins)
        tag: launchpad git tag to pull snapcraft instructions from (ie, git.launchpad.net/snap-kubectl)
        repo: launchpad git repo (git+ssh://$LPCREDS@git.launchpad.net/snap-kubectl)

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

        if not tracks:
            tracks = enums.SNAP_K8S_TRACK_MAP[version]

        params = {
            "name": self.name,
            "owner": "k8s-jenkaas-admin",
            "version": version,
            "branch": branch,
            "repo": self.repo,
            "track": tracks,
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


class SnapKubeApiServerRepoModel(SnapBaseRepoModel):
    def __init__(self):
        super().__init__()
        self.name = "kube-apiserver"
        self.git_user = "k8s-team-ci"
        self.repo = f"git+ssh://{self.git_user}@git.launchpad.net/snap-{self.name}"


class SnapKubeControllerManagerRepoModel(SnapBaseRepoModel):
    def __init__(self):
        super().__init__()
        self.name = "kube-controller-manager"
        self.git_user = "k8s-team-ci"
        self.repo = f"git+ssh://{self.git_user}@git.launchpad.net/snap-{self.name}"


class SnapKubeProxyRepoModel(SnapBaseRepoModel):
    def __init__(self):
        super().__init__()
        self.name = "kube-proxy"
        self.git_user = "k8s-team-ci"
        self.repo = f"git+ssh://{self.git_user}@git.launchpad.net/snap-{self.name}"


class SnapKubeSchedulerRepoModel(SnapBaseRepoModel):
    def __init__(self):
        super().__init__()
        self.name = "kube-scheduler"
        self.git_user = "k8s-team-ci"
        self.repo = f"git+ssh://{self.git_user}@git.launchpad.net/snap-{self.name}"


class SnapKubectlRepoModel(SnapBaseRepoModel):
    def __init__(self):
        super().__init__()
        self.name = "kubectl"
        self.git_user = "k8s-team-ci"
        self.repo = f"git+ssh://{self.git_user}@git.launchpad.net/snap-{self.name}"


class SnapKubeadmRepoModel(SnapBaseRepoModel):
    def __init__(self):
        super().__init__()
        self.name = "kubeadm"
        self.git_user = "k8s-team-ci"
        self.repo = f"git+ssh://{self.git_user}@git.launchpad.net/snap-{self.name}"


class SnapKubeletRepoModel(SnapBaseRepoModel):
    def __init__(self):
        super().__init__()
        self.name = "kubelet"
        self.git_user = "k8s-team-ci"
        self.repo = f"git+ssh://{self.git_user}@git.launchpad.net/snap-{self.name}"


class SnapKubernetesTestRepoModel(SnapBaseRepoModel):
    def __init__(self):
        super().__init__()
        self.name = "kubernetes-test"
        self.git_user = "k8s-team-ci"
        self.repo = f"git+ssh://{self.git_user}@git.launchpad.net/snap-{self.name}"
