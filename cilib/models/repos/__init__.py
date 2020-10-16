import semver
from cilib import git, version


class BaseRepoModel:
    """Represents the upstream source to be included in the debian packaging"""

    def __init__(self):
        self.repo = None
        self.git_user = None
        self.name = None

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

    def latest_branch_from_major_minor(self, major_minor, include_prerelease=False):
        """Grabs latest known branch semver for a major.minor release"""
        _branches = []
        for branch in self.branches:
            try:
                branch_version = version.parse(branch)
                if not include_prerelease and branch_version["prerelease"] is not None:
                    continue

                if (
                    major_minor
                    == f"{branch_version['major']}.{branch_version['minor']}"
                ):
                    _branches.append(version.normalize(branch))
            except:
                continue
        return str(max(map(semver.VersionInfo.parse, _branches)))

    def tags_from_semver_point(self, starting_semver):
        """Returns a list of tags from a starting semantic version"""
        tags = []
        for tag in self.tags:
            try:
                if version.compare(tag, starting_semver):
                    tags.append(tag)
            except Exception as error:
                print(error)
                continue
        return tags

    def tags_subset(self, alt_model):
        """Grabs a subset of tags from a another repo model"""
        return list(set(self.tags) - set(alt_model.tags))

    def tags_subset_semver_point(self, alt_model, starting_semver):
        """Grabs a subset of tags from a semantic version starting point"""
        return list(
            set(self.tags_from_semver_point(starting_semver))
            - set(alt_model.tags_from_semver_point(starting_semver))
        )
