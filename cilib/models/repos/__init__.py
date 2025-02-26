from cilib import git, version, log
from drypy.patterns import sham
from pathlib import Path
from urllib.parse import urlparse

import requests


class BaseRepoModel(log.DebugMixin):
    """Represents the upstream source to be included in the debian packaging"""

    def __init__(self, repo=None, git_user=None, name=None):
        self.repo = repo
        self.git_user = git_user
        self.name = name

    def __str__(self):
        return self.repo

    def cat(self, branch, path):
        """Cat file from a git repo"""
        parsed = urlparse(self.repo)
        if "git.launchpad.net" in parsed.netloc:
            """
            Launchpad supports viewing files directly from the web interface
            for example:
                repo: git+ssh://k8s-team-ci@git.launchpad.net/snap-kube-apiserver
                branch: v1.28.13
                file: /snapcraft.yaml

                becomes
                https://k8s-team-ci@git.launchpad.net/snap-kubectl/plain/snapcraft.yaml?h=v1.28.13
            """
            full_path = Path("/") / path
            url = f"https://{parsed.netloc}{parsed.path}/plain{full_path}?h={branch}"
        elif "github.com" in parsed.netloc:
            """
            Github supports viewing files directly from the web interface
            https://raw.githubusercontent.com/kubernetes/kubernetes/refs/tags/v1.32.0/.go-version
            """
            full_path = Path("/") / path
            url = f"https://raw.githubusercontent.com{parsed.path}/refs/tags/{branch}{full_path}"
        else:
            raise NotImplementedError("Only launchpad.net and github.com supported")

        response = requests.get(url)
        if response.status_code == 200:
            return response.text
        elif response.status_code == 404:
            raise FileNotFoundError(f"File not found: {url}")
        else:
            raise Exception(f"Failed to fetch {url}: {response.status_code}")

    def clone(self, **subprocess_kwargs):
        """Clone package repo"""
        git.clone(self.repo, **subprocess_kwargs)

    def checkout(
        self, ref="master", new_branch=False, force=False, **subprocess_kwargs
    ):
        """Checkout ref"""
        git.checkout(ref, new_branch, force, **subprocess_kwargs)

    def commit(self, message, **subprocess_kwargs):
        """Add commit to repo"""
        git.commit(message, **subprocess_kwargs)

    def add(self, files, **subprocess_kwargs):
        """Add files to git repo"""
        git.add(files, **subprocess_kwargs)

    def status(self, **subprocess_kwargs):
        """Diff git repo"""
        return git.status(**subprocess_kwargs)

    @sham
    def push(self, origin="origin", ref="master", **subprocess_kwargs):
        """Pushes commit to repo"""
        git.push(origin, ref, **subprocess_kwargs)

    def fetch(self, origin="origin", **subprocess_kwargs):
        """Fetch package repo"""
        git.fetch(origin, **subprocess_kwargs)

    def merge(self, origin="origin", ref="master", **subprocess_kwargs):
        """Merge branch repo"""
        git.merge(origin, ref, **subprocess_kwargs)

    def remote_add(self, origin, url, **subprocess_kwargs):
        """Add a remote to git repo"""
        git.remote_add(origin, url, **subprocess_kwargs)

    @property
    def tags(self, **subprocess_kwargs):
        """Grabs git remote tags"""
        return git.remote_tags(self.repo, **subprocess_kwargs)

    @property
    def branches(self, **subprocess_kwargs):
        """Grabs remote branches"""
        return git.remote_branches(self.repo, **subprocess_kwargs)

    def latest_branch_from_major_minor(self, major_minor, exclude_pre=False):
        """Grabs latest known branch semver for a major.minor release"""
        return self._latest_from_semver(self.branches, major_minor, exclude_pre)

    def latest_tag_from_major_minor(self, major_minor, exclude_pre=False):
        """Grabs latest known tag semver for a major.minor release"""
        return self._latest_from_semver(self.tags, major_minor, exclude_pre)

    def branches_from_semver_point(self, starting_semver):
        """Returns a list of branches from a starting semantic version"""
        return self._semvers_from_point(self.branches, starting_semver)

    def tags_from_semver_point(self, starting_semver):
        """Returns a list of tags from a starting semantic version"""
        return self._semvers_from_point(self.tags, starting_semver)

    def tags_subset(self, alt_model):
        """Grabs a subset of tags from a another repo model"""
        return list(set(self.tags) - set(alt_model.tags))

    def tags_subset_semver_point(self, alt_model, starting_semver):
        """Grabs a subset of tags from a semantic version starting point"""
        return list(
            set(self.tags_from_semver_point(starting_semver))
            - set(alt_model.tags_from_semver_point(starting_semver))
        )

    # private

    def _latest_from_semver(self, semvers, major_minor, exclude_pre=False):
        """Grabs latest semver from list of semvers"""
        _semvers = []
        for _semver in semvers:
            try:
                semver_version = version.parse(_semver)
                if exclude_pre and semver_version.prerelease is not None:
                    continue
                if major_minor == f"{semver_version.major}.{semver_version.minor}":
                    _semvers.append(str(semver_version))
            except:
                continue
        if not _semvers:
            return None
        max_ver = max(map(version.parse, _semvers))

        # Grab the branches for max_ver to determine if there are any patches that need to be applied
        # If any branches has +patch.X defined we use that build information to determine the latest patched
        # version of that particular major.minor.patch level and that will be built instead.
        branches = self.branches_from_semver_point(f"{max_ver.major}.{max_ver.minor}.0")
        patched_branches = []
        for branch in branches:
            if (
                version.normalize(branch)
                == f"{max_ver.major}.{max_ver.minor}.{max_ver.patch}"
                and "patch" in branch
            ):
                patched_branches.append(version.parse(branch).build)

        if patched_branches:
            max_patched = max(patched_branches)
            return str(f"{max_ver}+{max_patched}")

        return str(max_ver)

    def _semvers_from_point(self, semvers, starting_semver):
        """Grabs all semvers from branches or tags at starting semver point"""
        _semvers = []
        for _semver in semvers:
            try:
                if version.greater(_semver, starting_semver):
                    _semvers.append(_semver)
            except ValueError:
                self.debug(f"Ignoring non-semver branch: {_semver}")
                continue
            except Exception:
                self.exception(
                    f"Unexpected semver error while parsing branch: {_semver}"
                )
                continue
        return _semvers
