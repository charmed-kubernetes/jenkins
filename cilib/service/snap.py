"""Snap service object


Handles the building, syncing of snaps


TODO: surl

for surl:
1- get a valid macaroon, resusable by name: $ surl -a package-access-prod -e "email addr" -s production
2- get the channel map for your snap: surl -a package-access-prod -X GET https://dashboard.snapcraft.io/api/v2/snaps/cdk-addons/channel-map | jq .
"""

import os
import tempfile
import semver
from jinja2 import Template
from pathlib import Path
from pymacaroons import Macaroon
from cilib import lp, idm, enums
from cilib.run import cmd_ok
from cilib.log import DebugMixin
from drypy.patterns import sham


class SnapService(DebugMixin):
    def __init__(self, snap_model, upstream_model):
        self.snap_model = snap_model
        self.name = self.snap_model.name
        self.upstream_model = upstream_model

    @property
    def missing_branches(self):
        """Returns any missing branches in our snap git repos that are defined upstream"""
        upstream_tags = self.upstream_model.tags_from_semver_point(
            enums.K8S_STARTING_SEMVER
        )
        snap_branches = self.snap_model.base.branches_from_semver_point(
            enums.K8S_STARTING_SEMVER
        )
        return list(set(upstream_tags) - set(snap_branches))

    def sync_from_upstream(self):
        """Syncs branches from upstream tags"""
        if not self.missing_branches:
            self.log(f"All branches are synced, nothing to do here.")
            return

        for branch in self.missing_branches:
            self.log(f"Processing branch {branch}")
            with tempfile.TemporaryDirectory() as tmpdir:
                src_path = Path(tmpdir) / self.snap_model.src
                self.snap_model.base.clone(cwd=tmpdir)
                self.snap_model.base.checkout(
                    branch, new_branch=True, cwd=str(src_path)
                )

                snapcraft_fn = src_path / "snapcraft.yaml"
                snapcraft_fn_tpl = src_path / "snapcraft.yaml.in"

                k8s_major_minor = semver.VersionInfo.parse(branch.lstrip("v"))

                snapcraft_yml_context = {
                    "snap_version": branch.lstrip("v"),
                    "patches": [],
                    "go_version": enums.K8S_GO_MAP.get(
                        f"{k8s_major_minor.major}.{k8s_major_minor.minor}",
                        "go/1.17/stable",
                    ),
                }

                # Starting with 1.19 and beyond, build snaps with a base snap of core18 or
                # whatever the fresh catch of the day is
                if semver.compare(str(k8s_major_minor), "1.19.0") >= 0:
                    snapcraft_yml_context["base"] = "core18"

                self.log(f"Writing template vars {snapcraft_yml_context}")
                snapcraft_yml = snapcraft_fn_tpl.read_text()
                snapcraft_yml = self.render(snapcraft_fn_tpl, snapcraft_yml_context)
                snapcraft_fn.write_text(snapcraft_yml)

                self.log(f"Committing {branch}")
                self.snap_model.base.add([str(snapcraft_fn)], cwd=str(src_path))
                self.snap_model.base.commit(
                    f"Creating branch {branch}", cwd=str(src_path)
                )
                self.snap_model.base.push(ref=branch, cwd=str(src_path))

    def sync_stable_track_snaps(self):
        """Keeps current stable version snap builds in sync with latest track"""
        self.snap_model.version = enums.K8S_STABLE_VERSION

        for arch in enums.K8S_SUPPORT_ARCHES:
            self.log(
                f"Checking snaps in version {enums.K8S_STABLE_VERSION} for arch {arch}"
            )
            max_track_rev = self.snap_model.latest_revision(
                track=f"{enums.K8S_STABLE_VERSION}/stable",
                arch=arch,
            )
            max_stable_rev = self.snap_model.latest_revision(
                track=f"latest/stable", arch=arch
            )
            if max_stable_rev < max_track_rev:
                self.log(
                    f"Track revisions do not match {max_track_rev} != {max_stable_rev}, syncing stable snaps to latest track"
                )
                for _track in ["stable", "candidate", "beta", "edge"]:
                    self._release(max_track_rev, _track)
            else:
                self.log(
                    f"{self.snap_model.name} revision {max_stable_rev} == {max_track_rev}, no promotion needed."
                )

    def sync_all_track_snaps(self):
        """Keeps snap builds current with latest releases"""
        supported_versions = list(enums.SNAP_K8S_TRACK_MAP.keys())
        for _version in supported_versions:
            for arch in enums.K8S_SUPPORT_ARCHES:
                self.log(f"> Checking snaps in version {_version} for arch {arch}")

                # Set the current version in the snap model
                self.snap_model.version = _version

                exclude_pre = True
                if _version == enums.K8S_NEXT_VERSION:
                    self.log(
                        f"Next development version triggered, will query pre-releases."
                    )
                    # Only pull in pre-releases if building for the next development version
                    exclude_pre = False

                max_rev = self.snap_model.latest_revision(
                    track=f"{_version}/edge",
                    arch=arch,
                )

                if max_rev:
                    latest_snap_version = self.snap_model.store.version_from_rev(
                        max_rev, arch
                    )
                    self.log(
                        f"Found snap version {str(latest_snap_version)} at revision {max_rev} for {_version}/edge"
                    )
                else:
                    latest_snap_version = semver.VersionInfo.parse("0.0.0")
                    self.log(f"No revision or snap version found, assuming new version")
                latest_branch_version = (
                    self.snap_model.base.latest_branch_from_major_minor(
                        _version, exclude_pre
                    )
                )
                self.log(f"Latest branch version {latest_branch_version}")

                # Skip building development version if a stable version actually
                # exists, for example, if 1.21 is in development but there
                # exists a 1.21.1-rc.0 AND 1.21.0 we do not want to build
                # 1.21.1-rc.0 as anything with stable releases are considered
                # usable by end users.
                if (
                    _version == enums.K8S_NEXT_VERSION
                    and not semver.VersionInfo.parse(latest_branch_version).prerelease
                ):
                    self.log(
                        f"This version has a non prerelease {str(latest_branch_version)} in our next development build, skipping."
                    )
                    continue

                if (
                    semver.compare(str(latest_branch_version), str(latest_snap_version))
                    > 0
                ):
                    self.log(
                        f"Found new branch {str(latest_branch_version)} > {str(latest_snap_version)}, building new snap"
                    )
                    self._create_recipe(_version, f"v{str(latest_branch_version)}")
                else:
                    self.log(
                        f"> Versions match {str(latest_branch_version)} == {str(latest_snap_version)}, not building a new snap"
                    )

    def build_snap_from_branch(self, branch_version):
        """Builds a snap from a certain branch version"""
        branch_version_parsed = semver.VersionInfo.parse(branch_version)
        self.snap_model.version = (
            f"{branch_version_parsed.major}.{branch_version_parsed.minor}"
        )

        self.log(
            f"Building snap for {str(branch_version_parsed)} into {self.snap_model.tracks}"
        )
        self._create_recipe(self.snap_model.version, f"v{str(branch_version_parsed)}")

    def render(self, tmpl_file, context):
        """Renders a jinja template with context"""
        template = Template(tmpl_file.read_text(), keep_trailing_newline=True)
        return template.render(context)

    # private
    @sham
    def _release(self, max_track_rev, track):
        """Runs snapcraft release"""
        ret = cmd_ok(
            f"snapcraft release {self.snap_model.name} {max_track_rev} {track}",
            echo=self.log,
        )
        if not ret.ok:
            raise Exception(
                f"Failed to promote {self.snap_model.name} (rev: {max_track_rev}) to track {_track}"
            )

    @sham
    def _create_recipe(self, version, branch):
        """ Creates an new snap recipe in Launchpad

        tag: launchpad git tag to pull snapcraft instructions from (ie, git.launchpad.net/snap-kubectl)

        # Note: this account would need access granted to the snaps it want's to publish from the snapstore dashboard
        snap_recipe_email: snapstore email for being able to publish snap recipe from launchpad to snap store
        snap_recipe_password: snapstore password for account being able to publish snap recipe from launchpad to snap store

        Usage:

        snap.py create-snap-recipe --snap kubectl --version 1.13 --tag v1.13.2 \
          --track 1.13/edge/hotfix-LP123456 \
          --repo git+ssh://$LPCREDS@git.launchpad.net/snap-kubectl \
          --owner k8s-jenkaas-admins \
          --snap-recipe-email myuser@email.com \
          --snap-recipe-password aabbccddee

        """
        params = {
            "name": self.snap_model.name,
            "owner": "k8s-jenkaas-admins",
            "version": version,
            "branch": branch,
            "repo": self.snap_model.repo,
            "track": self.snap_model.tracks,
        }

        self.log(f"> Creating recipe for {params}")

        snap_recipe_email = os.environ.get("K8STEAMCI_USR")
        snap_recipe_password = os.environ.get("K8STEAMCI_PSW")

        _client = lp.Client(stage="production")
        _client.login()

        snap_recipe = _client.create_or_update_snap_recipe(**params)
        caveat_id = snap_recipe.beginAuthorization()
        cip = idm.CanonicalIdentityProvider(
            email=snap_recipe_email, password=snap_recipe_password
        )
        discharge_macaroon = cip.get_discharge(caveat_id).json()
        discharge_macaroon = Macaroon.deserialize(
            discharge_macaroon["discharge_macaroon"]
        )
        snap_recipe.completeAuthorization(
            discharge_macaroon=discharge_macaroon.serialize()
        )
        snap_recipe.requestBuilds(archive=_client.archive(), pocket="Updates")
