""" Repo classes for downstream deb packages """

from . import BaseRepoModel
from cilib import enums
from cilib.log import DebugMixin
import os
import sh
import re
import semver


class DebBaseRepoModel(DebugMixin):
    name = None

    def __init__(self):
        self.version = None
        self.git_user = "k8s-team-ci"
        self.repo = f"git+ssh://{self.git_user}@git.launchpad.net/{self.name}"
        self.src = f"{self.name}"

    def __str__(self):
        return f"<{self.name}>"

    @property
    def base(self):
        return BaseRepoModel(repo=self.repo, git_user=self.git_user, name=self.name)


class DebCriToolsRepoModel(DebBaseRepoModel):
    def __init__(self):
        self.name = "cri-tools"
        super(DebCriToolsRepoModel, self).__init__()


class DebKubeadmRepoModel(DebBaseRepoModel):
    def __init__(self):
        self.name = "kubeadm"
        super(DebKubeadmRepoModel, self).__init__()


class DebKubectlRepoModel(DebBaseRepoModel):
    def __init__(self):
        self.name = "kubectl"
        super(DebKubectlRepoModel, self).__init__()


class DebKubeletRepoModel(DebBaseRepoModel):
    def __init__(self):
        self.name = "kubelet"
        super(DebKubeletRepoModel, self).__init__()


class DebKubernetesCniRepoModel(DebBaseRepoModel):
    def __init__(self):
        self.name = "kubernetes-cni"
        super(DebKubernetesCniRepoModel, self).__init__()
