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
