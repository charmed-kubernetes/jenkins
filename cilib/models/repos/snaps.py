""" Repo classes for downstream snaps """

from . import BaseRepoModel
from pymacaroons import Macaroon
from cilib import lp, idm, enums
import os


class SnapBaseRepoModel(BaseRepoModel):
    def __init__(self):
        super().__init__()
        self.git_user = "k8s-team-ci"
        self.repo = f"git+ssh://{self.git_user}@git.launchpad.net/snap-{snap}"
        self.snap_recipe_email=os.environ.get("K8STEAMCI_USR")
        self.snap_recipe_password=os.environ.get("K8STEAMCI_PSW")

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
            email=self.snap_recipe_email, password=self.snap_recipe_password
        )
        discharge_macaroon = cip.get_discharge(caveat_id).json()
        discharge_macaroon = Macaroon.deserialize(discharge_macaroon["discharge_macaroon"])
        snap_recipe.completeAuthorization(discharge_macaroon=discharge_macaroon.serialize())
        snap_recipe.requestBuilds(archive=_client.archive(), pocket="Updates")


class SnapKubeApiServerRepoModel(SnapBaseRepoModel):
    def __init__(self):
        self.name = "kube-apiserver"
        super().__init__()

class SnapKubeControllerManagerRepoModel(BaseRepoModel):
    def __init__(self):
        self.name = "kube-controller-manager"
        super().__init__()

class SnapKubeProxyRepoModel(BaseRepoModel):
    def __init__(self):
        self.name = "kube-proxy"
        super().__init__()

class SnapKubeSchedulerRepoModel(BaseRepoModel):
    def __init__(self):
        self.name = "kube-scheduler"
        super().__init__()

class SnapKubectlRepoModel(BaseRepoModel):
    def __init__(self):
        self.name = "kubectl"
        super().__init__()

class SnapKubeadmRepoModel(BaseRepoModel):
    def __init__(self):
        self.name = "kubeadm"
        super().__init__()

class SnapKubeletRepoModel(BaseRepoModel):
    def __init__(self):
        self.name = "kubelet"
        super().__init__()

class SnapKubernetesTestRepoModel(BaseRepoModel):
    def __init__(self):
        self.name = "kubernetes-test"
        super().__init__()
