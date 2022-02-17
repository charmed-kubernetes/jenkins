""" Repo classes for downstream charms, layers, interfaces """

from . import BaseRepoModel
from cilib.log import DebugMixin
from cilib.git import default_gh_branch
import os
from urllib.parse import quote
from pathlib import Path


class CharmRepoModel(DebugMixin):
    name = None

    def __init__(self, name, upstream, downstream):
        self.name = name.replace(":", "-")
        self.git_user = quote(os.environ["CDKBOT_GH_USR"])
        self.password = quote(os.environ["CDKBOT_GH_PSW"])
        self.upstream = upstream
        self.downstream = downstream
        self.repo = f"https://{self.git_user}:{self.password}@github.com/{downstream}"
        self.src = str(Path(downstream).with_suffix("")).split("/")[-1]

    def __str__(self):
        return f"<{self.name}>"

    @property
    def base(self):
        return BaseRepoModel(repo=self.repo, git_user=self.git_user, name=self.name)

    def default_gh_branch(self, remote):
        """Determine the default GitHub branch for a repo.

        If the branch name cannot be determined, return 'master'.
        """
        # NB: ignore errors since not all CK layer repos come from github
        branch = default_gh_branch(
            remote, ignore_errors=True, auth=(self.git_user, self.password)
        )
        return branch or "master"

    @classmethod
    def load_repos(cls, repos):
        """Loads all repos and creates a model for each"""
        return [
            CharmRepoModel(layer_name, _repos["upstream"], _repos["downstream"])
            for layer_map in repos
            for layer_name, _repos in layer_map.items()
        ]
