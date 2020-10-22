import semver
from cilib import git, version, log


class BaseRepoModel:
    """Represents the upstream source to be included in the debian packaging"""

    def __init__(self, repo=None, git_user=None, name=None):
        self.repo = repo
        self.git_user = git_user
        self.name = name

    def __str__(self):
        return self.repo

    def clone(self, **subprocess_kwargs):
        """Clone package repo"""
        git.clone(self.repo, **subprocess_kwargs)

    def checkout(self, ref="master", **subprocess_kwargs):
        """Checkout ref"""
        git.checkout(ref, **subprocess_kwargs)

    def commit(self, message, **subprocess_kwargs):
        """Add commit to repo"""
        git.commit(message, **subprocess_kwargs)

    def add(self, files, **subprocess_kwargs):
        """Add files to git repo"""
        git.add(files, **subprocess_kwargs)

    def push(self, origin="origin", ref="master", **subprocess_kwargs):
        """Pushes commit to repo"""
        git.push(origin, ref, **subprocess_kwargs)

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
        return str(max(map(semver.VersionInfo.parse, _semvers)))

    def _semvers_from_point(self, semvers, starting_semver):
        """Grabs all semvers from branches or tags at starting semver point"""
        _semvers = []
        for _semver in semvers:
            try:
                if version.greater(_semver, starting_semver):
                    _semvers.append(_semver)
            except Exception as error:
                print(error)
                continue
        return _semvers
