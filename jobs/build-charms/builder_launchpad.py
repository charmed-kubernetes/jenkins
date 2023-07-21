""" Launchpad Charm Builder
"""

import zlib
import os
import re
import time
import urllib.request
import zipfile

from functools import cached_property
from pathlib import Path

from launchpadlib.launchpad import Launchpad
from lazr.restfulclient.errors import NotFound

from builder_local import Arch, Artifact, BuildEntity, BuildException


class LPBuildEntity(BuildEntity):
    """The launchpad build data class.

    Builds charms on launchpad with charm recipes
    """

    SNAP_CHANNEL = {"charmcraft": "latest/stable"}
    BUILD_STATES_PENDING = {
        "Needs building",
        "Currently building",
        "Uploading build",
        "Cancelling build",
    }
    BUILD_STATES_SUCCESS = {
        "Successfully built",
    }

    @staticmethod
    def _recipe_from_branch(branch: str):
        """Recipe names must be lowercase alphanumerics with allowed +, -, and ."""
        subbed = re.sub(r"[^0-9a-zA-Z\+\-\.]+", "-", branch)
        return subbed.lower()

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._lp_bugs = self.opts.get("bugs", "")
        self._lp_branch = self.branch
        self._lp_project_name = self._lp_bugs.rsplit("/")[-1]
        self._lp_recipe_name = self._recipe_from_branch(self._lp_branch)

        assert self.type == "Charm", "Only supports charm builds"
        assert "launchpad.net" in self._lp_bugs, "No associated with launchpad"

    @cached_property
    def _lp(self):
        creds = os.environ.get("LPCREDS", None)
        return Launchpad.login_with(
            application_name="k8s-jenkaas-bot",
            service_root="production",
            version="devel",
            credentials_file=creds,
        )

    @cached_property
    def _lp_project(self):
        """Link to the charm project in launchpad."""
        return self._lp.projects[self._lp_project_name]

    @cached_property
    def _lp_owner(self):
        """Link to the charm project's owner in launchpad."""
        return self._lp.people[self._lp_project.owner.name]

    @cached_property
    def _lp_recipe(self):
        """Lookup or create the charm recipe."""
        try:
            rec = self._lp.charm_recipes.getByName(
                owner=self._lp_owner,
                project=self._lp_project,
                name=self._lp_recipe_name,
            )
        except NotFound:
            self.echo(f"Creating recipe for branch :{self._lp_branch}")
            repo = self._lp.git_repositories.getDefaultRepository(
                target=self._lp_project
            )
            ref = repo.refs_collection_link.replace("refs", f"+ref/{self._lp_branch}")
            rec = self._lp.charm_recipes.new(
                name=self._lp_recipe_name,
                auto_build=False,
                auto_build_channels=self.SNAP_CHANNEL,
                git_ref=ref,
                owner=self._lp_owner,
                project=self._lp_project,
                store_channels=[],
                store_upload=False,
            )
        return rec

    def _lp_request_builds(self):
        """Request a charm build for this charm."""
        req = self._lp_recipe.requestBuilds(channels=self.SNAP_CHANNEL)
        self.echo("Waiting for charm recipe request")
        timeout = 5 * 60
        for _ in range(timeout):
            status = req.status
            if status == "Failed":
                raise BuildException(
                    f"Failed to request build {self.name} on launchpad"
                )
            if status == "Completed":
                break
            time.sleep(1.0)
            req.lp_refresh()
        return req.builds

    def _lp_complete_builds(self, builds):
        """Ensure that all the builds of a specified charm are completed."""
        incomplete_builds = {_.self_link for _ in builds}
        while incomplete_builds:
            for build in builds:
                if build.self_link not in incomplete_builds:
                    continue
                if (status := build.buildstate) in self.BUILD_STATES_PENDING:
                    self.echo(f"Waiting for {build.title}: build={status}")
                    build.lp_refresh()
                else:
                    self.echo(f"Completed {build.title}: build={status}")
                    incomplete_builds.remove(build.self_link)
            if incomplete_builds:
                time.sleep(30.0)
        for build in builds:
            if build.buildstate not in self.BUILD_STATES_SUCCESS:
                raise BuildException(f"Failed to build {build.title} on launchpad")
        return builds

    @staticmethod
    def _lp_charm_filename_from_build(build):
        """Read the build_log to determine the charm file name.

        Currently, this is accomplished by reading the buildlog
        and looking for a keyword, knowing the next line is the charm name
        """

        def find_packed_charm(lines):
            found, keyword = False, b"Charms packed:"
            for line in lines:
                if line.startswith(keyword):
                    found |= True
                elif found:
                    yield line.decode().strip()
                    found = False

        with urllib.request.urlopen(build.build_log_url) as f:
            fp = find_packed_charm(
                zlib.decompress(f.read(), 16 + zlib.MAX_WBITS).splitlines()
            )
            return next(fp)

    def _lp_build_download(self, build, dst_target: Path) -> Artifact:
        charm_file = self._lp_charm_filename_from_build(build)
        dl_link = build.web_link + f"/+files/{charm_file}"
        with urllib.request.urlopen(dl_link) as src:
            target = dst_target / charm_file
            with target.open("wb") as dst:
                dst.write(src.read())
            self.echo(f"Downloaded {build.title}")
            return Artifact(Arch[build.title.split(" ")[0].upper()], target)

    def _lp_amend_git_version(self):
        """Write the git sha into the charm."""
        git_sha = self.commit(short=True)
        for artifact in self.artifacts:
            zip = zipfile.ZipFile(artifact.charm_or_bundle, "a")
            zip.writestr("version", git_sha + "\n")

    def charm_build(self):
        """Perform a build using a launchpad charm recipe."""
        self.echo(f"Starting a build of {self.name} on launchpad")
        request = self._lp_request_builds()
        builds = self._lp_complete_builds(request)
        download_path = Path(self.src_path)
        self.artifacts = [
            self._lp_build_download(build, download_path) for build in builds
        ]
        self._lp_amend_git_version()
