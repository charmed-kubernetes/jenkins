""" Launchpad Charm Builder
"""

import hashlib
import os
import re
import time
import urllib.request
import zipfile
import zlib

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

    SNAP_CHANNEL = {"charmcraft": "2.x/stable"}
    BUILD_STATES_PENDING = {
        "Cancelling build",
        "Currently building",
        "Gathering build output",
        "Needs building",
        "Uploading build",
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
        cred_file = os.environ.get("LPCREDS", None)
        creds_local = os.environ.get("LPLOCAL", None)
        if cred_file:
            parser = ConfigParser()
            parser.read(cred_file)
            return Launchpad.login_with(
                application_name=parser["1"]["consumer_key"],
                service_root="production",
                version="devel",
                credentials_file=cred_file,
            )
        elif creds_local:
            return Launchpad.login_with(
                "localhost",
                "production",
                version="devel",
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
    def _lp_channels(self):
        channels = self.SNAP_CHANNEL
        charmcraft_channel_file = Path(self.src_path) / ".charmcraft-channel"
        if charmcraft_channel_file.exists():
            channels["charmcraft"] = charmcraft_channel_file.read_text().strip()
            self.echo(
                f"Using channel from {charmcraft_channel_file}: {channels['charmcraft']}"
            )
        return channels

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
                auto_build_channels={},
                build_path=self.opts.get("subdir"),
                description=f"Recipe for {self._lp_project} {self._lp_branch}",
                git_ref=ref,
                owner=self._lp_owner,
                project=self._lp_project,
                store_channels=[],
                store_upload=False,
            )
        rec.auto_build_channels = self._lp_channels
        rec.lp_save()
        return rec

    def _lp_build_log(self, build: Resource) -> str:
        """Request the build log of a completed build."""
        if build.buildstate in self.BUILD_STATES_PENDING:
            return ""
        if cache := self._lp_build_log_cache.get(build.self_link):
            return cache

        with urllib.request.urlopen(build.build_log_url) as f:
            contents = zlib.decompress(f.read(), 16 + zlib.MAX_WBITS)
        self._lp_build_log_cache[build.self_link] = c_str = contents.decode()
        return c_str

    def _lp_request_builds(self) -> List[Resource]:
        """Request a charm build for this charm."""
        req = self._lp_recipe.requestBuilds(channels=self._lp_channels)
        self.echo("Waiting for charm recipe request")
        timeout = 5 * 60
        for _ in range(timeout):
            status = req.status
            if status == "Failed":
                err_msg = f"Failed requesting launchpad build {self.entity}, aborting"
                raise BuildException(err_msg)
            if status == "Completed":
                self.echo(f"Build recipe started @ {self._lp_recipe.web_link}")
                break
            time.sleep(1.0)
            req.lp_refresh()
        return [build for build in req.builds]

    def _lp_complete_builds(self, builds: List[Resource]):
        """Ensure that all the builds of a specified charm are completed."""
        pending_builds = {_.self_link for _ in builds}
        failed_builds = set()
        start_time = datetime.now()
        while pending_builds and not failed_builds:
            for build in builds:
                if build.self_link not in pending_builds:
                    continue
                build.lp_refresh()
                dt = datetime.now() - start_time
                if (state := build.buildstate) in self.BUILD_STATES_PENDING:
                    status = f"Waiting for {build.title} status='{state}' elapsed={dt}"
                else:
                    status = f"Completed {build.title} status='{state}' elapsed={dt}"
                    pending_builds.remove(build.self_link)
                    if state not in self.BUILD_STATES_SUCCESS:
                        failed_builds.add(build.self_link)
                self.echo(status)

            if pending_builds and not failed_builds:
                time.sleep(30.0)
        for build_link in pending_builds:
            # If one build fails, cancel the others first
            build = next(_ for _ in builds if _.self_link == build_link)
            if build.can_be_cancelled:
                self.echo(f"Cancelling {build.title}...")
                build.cancel()
        for build in builds:
            if build.buildstate not in self.BUILD_STATES_SUCCESS:
                err_msg = (
                    f"Failed launchpad build {self.entity} due to "
                    f"unsuccessful build state '{build.buildstate}'."
                )

                self.echo(err_msg + "\n" + self._lp_build_log(build))
                raise BuildException(err_msg)
        return builds

    def _lp_charm_filename_from_build(self, build) -> str:
        """Determine the charm file name of a particular build.

        Currently, this is accomplished by reading the buildlog
        and looking for a regex match of the charmn name.

        replace once LP#2028406 is fixed
        """

        content = self._lp_build_log(build)
        charm_file_matches = re.findall(r"([\w\-\.]+\.charm)", content, re.MULTILINE)
        uniq = set(charm_file_matches)
        if not uniq:
            err_msg = (
                f"Failed launchpad build {self.entity} due to "
                "not finding a named packed charm."
            )
            raise BuildException(err_msg)
        elif len(uniq) > 1:
            err_msg = (
                f"Failed launchpad build {self.entity} due to "
                "not finding too many named packed charms."
                "Found charm files: " + ", ".join(uniq)
            )
            raise BuildException(err_msg)

        return uniq.pop()

    def _lp_build_download(self, build, dst_target: Path) -> Artifact:
        """Download charm file for a launchpad build."""
        charm_file = self._lp_charm_filename_from_build(build)
        dl_link = build.web_link + f"/+files/{charm_file}"
        with urllib.request.urlopen(dl_link) as src:
            buffer = src.read()

        md5sum = hashlib.md5(buffer).hexdigest()
        target = dst_target / charm_file
        with target.open("wb") as dst:
            dst.write(buffer)

        self.echo(f"Downloaded {build.title} md5sum={md5sum}")
        return Artifact.from_charm(target)

    def _lp_amend_git_version(self):
        """Write the git sha into the charm."""
        git_sha = self.commit(short=True)
        for artifact in self.artifacts:
            zip = zipfile.ZipFile(artifact.charm_or_bundle, "a")
            zip.writestr("version", git_sha + "\n")

    def _lp_request_sync(self):
        """Ensure that the upstream github repo is in sync with the launchpad repo."""
        self.echo(f"Syncing lp branch from upstream: {self._lp_branch}")
        git_sha = self.commit()
        repo = self._lp.git_repositories.getDefaultRepository(target=self._lp_project)

        def _shas_in_sync():
            commit_shas = [
                branch.commit_sha1
                for branch in repo.branches_collection
                if branch.path == f"refs/heads/{self._lp_branch}"
            ]
            return commit_shas == [git_sha]

        if _shas_in_sync():
            return

        start_time = datetime.now()
        repo.code_import.requestImport()
        while not _shas_in_sync():
            dt = datetime.now() - start_time
            status = f"Waiting for {self._lp_branch} sha256='{git_sha}' elapsed={dt}"
            self.echo(status)
            time.sleep(30.0)

    def charm_build(self):
        """Perform a build using a launchpad charm recipe."""
        self.echo(f"Starting a build of {self.name} on launchpad")
        self._lp_request_sync()
        request = self._lp_request_builds()
        builds = self._lp_complete_builds(request)
        download_path = Path(self.src_path)
        self.artifacts = [
            self._lp_build_download(build, download_path) for build in builds
        ]
        self._lp_amend_git_version()
