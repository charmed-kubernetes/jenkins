""" Launchpad Charm Builder
"""

import zlib
import os
import re
import time
import urllib.request
import zipfile

from configparser import ConfigParser
from datetime import datetime
from functools import cached_property
from pathlib import Path
from typing import List

from launchpadlib.launchpad import Launchpad
from lazr.restfulclient.errors import NotFound
from lazr.restfulclient.resource import Resource

from builder_local import Artifact, BuildEntity, BuildException


class LPBuildEntity(BuildEntity):
    """The launchpad builder entity class.

    Builds charms on launchpad with charm recipes, then downloads locally
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

    def _lp_recipe_from_branch(self, branch: str):
        """Recipe names must be lowercase alphanumerics with allowed +, -, and ."""
        subbed = re.sub(r"[^0-9a-zA-Z\+\-\.]+", "-", branch)
        return f"{self.name}-{subbed.lower()}"

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._lp_bugs = self.opts.get("bugs", "")
        self._lp_branch = self.branch
        self._lp_project_name = self._lp_bugs.rsplit("/")[-1]
        self._lp_recipe_name = self._lp_recipe_from_branch(self._lp_branch)
        self._lp_build_log_cache = {}

        assert self.type == "Charm", "Only supports charm builds"
        assert "launchpad.net" in self._lp_bugs, "No associated with launchpad"

    @cached_property
    def _lp(self):
        """Use launchpad credentials to interact with launchpad."""
        creds = os.environ.get("LPCREDS", None)
        parser = ConfigParser()
        parser.read(creds)
        return Launchpad.login_with(
            application_name=parser["1"]["consumer_key"],
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
                build_path=self.opts.get("subdir", ""),
                git_ref=ref,
                owner=self._lp_owner,
                project=self._lp_project,
                store_channels=[],
                store_upload=False,
            )
        return rec

    def _lp_build_log(self, build: Resource) -> str:
        """Request the build log of a completed build."""
        if build.buildstate in self.BUILD_STATES_PENDING:
            return ""
        if cache := self._lp_build_log_cache.get(build.self_link):
            return cache

        with urllib.request.urlopen(build.build_log_url) as f:
            contents = zlib.decompress(f.read(), 16 + zlib.MAX_WBITS)
        self._lp_build_log_cache[build.self_link] = contents
        return contents

    def _lp_request_builds(self) -> List[Resource]:
        """Request a charm build for this charm."""
        req = self._lp_recipe.requestBuilds(channels=self.SNAP_CHANNEL)
        self.echo("Waiting for charm recipe request")
        timeout = 5 * 60
        for _ in range(timeout):
            status = req.status
            if status == "Failed":
                err_msg = f"Failed requesting lauchpad build {self.entity}, aborting"
                raise BuildException(err_msg)
            if status == "Completed":
                break
            time.sleep(1.0)
            req.lp_refresh()
        return [build for build in req.builds]

    def _lp_complete_builds(self, builds: List[Resource]):
        """Ensure that all the builds of a specified charm are completed."""
        incomplete_builds = {_.self_link for _ in builds}
        start_time = datetime.now()
        while incomplete_builds:
            for build in builds:
                if build.self_link not in incomplete_builds:
                    continue
                build.lp_refresh()
                dt = datetime.now() - start_time
                if (status := build.buildstate) in self.BUILD_STATES_PENDING:
                    status = f"Waiting for {build.title} status='{status}' elapsed={dt}"
                else:
                    status = f"Completed {build.title} status='{status}' elapsed={dt}"
                    incomplete_builds.remove(build.self_link)
                self.echo(status)

            if incomplete_builds:
                time.sleep(30.0)
        for build in builds:
            if build.buildstate not in self.BUILD_STATES_SUCCESS:
                err_msg = f"Failed lauchpad build {self.entity}, aborting"
                self.echo(err_msg + "\n" + self._lp_build_log(build))
                raise BuildException(err_msg)
        return builds

    def _lp_charm_filename_from_build(self, build):
        """Determine the charm file name of a particular build.

        Currently, this is accomplished by reading the buildlog
        and looking for a keyword, knowing the next line is the charm name

        replace once LP#2028406 is fixed
        """

        def find_packed_charm(lines):
            found, keyword = False, b"Charms packed:"
            for line in lines:
                if line.startswith(keyword):
                    found |= True
                elif found:
                    yield line.decode().strip()
                    found = False

        fp = find_packed_charm(self._lp_build_log(build).splitlines())
        return next(fp)

    def _lp_build_download(self, build, dst_target: Path) -> List[Artifact]:
        """Download charm file for a launchpad build."""
        charm_file = self._lp_charm_filename_from_build(build)
        dl_link = build.web_link + f"/+files/{charm_file}"
        with urllib.request.urlopen(dl_link) as src:
            target = dst_target / charm_file
            with target.open("wb") as dst:
                dst.write(src.read())
            self.echo(f"Downloaded {build.title}")
            return Artifact.from_charm(target)

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
            artifact
            for build in builds
            for artifact in self._lp_build_download(build, download_path)
        ]
        self._lp_amend_git_version()
