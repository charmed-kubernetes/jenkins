from . import BaseRepoModel


class UpstreamKubernetesRepoModel(BaseRepoModel):
    def __init__(self):
        super(UpstreamKubernetesRepoModel, self).__init__()
        self.name = "kubernetes"
        self.repo = "https://github.com/kubernetes/kubernetes"


class InternalKubernetesRepoModel(BaseRepoModel):
    def __init__(self):
        super(InternalKubernetesRepoModel, self).__init__()
        self.name = "k8s-internal-mirror"
        self.git_user = "k8s-team-ci"
        self.repo = f"git+ssh://{self.git_user}@git.launchpad.net/{self.name}"
        self.source = UpstreamKubernetesRepoModel()


class CriToolsUpstreamRepoModel(BaseRepoModel):
    def __init__(self):
        super(CriToolsUpstreamRepoModel, self).__init__()
        self.name = "cri-tools"
        self.repo = f"https://github.com/kubernetes-sigs/{self.name}.git"


class InternalCriToolsRepoModel(BaseRepoModel):
    def __init__(self):
        super(InternalCriToolsRepoModel, self).__init__()
        self.name = "cri-tools"
        self.git_user = "k8s-team-ci"
        self.repo = f"git+ssh://{self.git_user}@git.launchpad.net/{self.name}"


class CNIPluginsUpstreamRepoModel(BaseRepoModel):
    def __init__(self):
        super(CNIPluginsUpstreamRepoModel, self).__init__()
        self.name = "plugins"
        self.repo = f"https://github.com/containernetworking/{self.name}.git"


class InternalCNIPluginsRepoModel(BaseRepoModel):
    def __init__(self):
        super(InternalCNIPluginsRepoModel, self).__init__()
        self.name = "kubernetes-cni-internal"
        self.git_user = "k8s-team-ci"
        self.repo = f"git+ssh://{self.git_user}@git.launchpad.net/{self.name}"
