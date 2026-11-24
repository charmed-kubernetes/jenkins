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
from time import monotonic

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
        self._lp_build_request = None
        self._lp_request_deadline = None
        self._lp_builds = None

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
        channels = self.SNAP_CHANNEL.copy()
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

    def _lp_builds_ready(self):
        """Check the builds once; cancel siblings if a build failed."""
        pending = []
        failed = None
        for build in self._lp_builds:
            if build.buildstate in self.BUILD_STATES_SUCCESS:
                continue
            build.lp_refresh()
            state = build.buildstate
            if state in self.BUILD_STATES_PENDING:
                pending.append(build)
                self.echo(f"Waiting for {build.title} status='{state}'")
            else:
                self.echo(f"Completed {build.title} status='{state}'")
                if state not in self.BUILD_STATES_SUCCESS and failed is None:
                    failed = build

        if failed is not None:
            for build in pending:
                if build.can_be_cancelled:
                    self.echo(f"Cancelling {build.title}...")
                    build.cancel()
            message = (
                f"Failed launchpad build {self.entity} due to "
                f"unsuccessful build state '{failed.buildstate}'."
            )
            self.echo(message + "\n" + self._lp_build_log(failed))
            raise BuildException(message)

        return not pending

    def _lp_charm_filename_from_build(self, build) -> str:
        """Determine the charm file name of a particular build.

        Currently, this is accomplished by reading the buildlog
        and looking for a regex match of the charmn name.

        replace once LP#2028406 is fixed
        """

        content = self._lp_build_log(build)
        charm_file_matches = re.findall(
            r"\s([\w\-\.@]+\.charm)\s", content, re.MULTILINE
        )
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

        sha256sum = hashlib.sha256(buffer).hexdigest()
        target = dst_target / charm_file
        with target.open("wb") as dst:
            dst.write(buffer)

        self.echo(f"Downloaded {build.title} sha256sum={sha256sum}")
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

    def submit_build(self):
        """Sync the checkout and submit a build without waiting for the result."""
        self.echo(f"Starting a build of {self.name} on launchpad")
        self._lp_request_sync()
        recipe = self._lp_recipe
        self._lp_build_request = recipe.requestBuilds(channels=self._lp_channels)
        self._lp_request_deadline = monotonic() + 5 * 60
        self.echo(f"Submitted build request @ {self._lp_build_request.web_link}")

    def collect_build(self):
        """Download a finished build, or return False if it is still pending."""
        if self._lp_builds is None:
            request = self._lp_build_request
            request.lp_refresh()
            if request.status == "Completed":
                self._lp_builds = list(request.builds)
                if not self._lp_builds:
                    raise BuildException(
                        f"No Launchpad builds created for {self.entity}"
                    )
            elif request.status == "Failed":
                raise BuildException(f"Failed requesting Launchpad build {self.entity}")
            elif monotonic() >= self._lp_request_deadline:
                raise BuildException(
                    f"Timed out requesting Launchpad build {self.entity}"
                )
            else:
                return False

        if not self._lp_builds_ready():
            return False
        download_path = Path(self.src_path)
        self.artifacts = [
            self._lp_build_download(build, download_path) for build in self._lp_builds
        ]
        self._lp_amend_git_version()
        return True
