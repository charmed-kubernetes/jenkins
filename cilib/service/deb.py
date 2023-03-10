"""Debian service object


Handles the building, syncing of debian packages
"""

import os
import tempfile
import semver
import textwrap
from functools import cached_property
from jinja2 import Template
from pathlib import Path
from pymacaroons import Macaroon
from cilib import lp, idm, enums
from cilib.models.ppa import PPACollection
from cilib.run import cmd_ok
from cilib.log import DebugMixin
from drypy.patterns import sham


class DebService(DebugMixin):
    def __init__(self, deb_model, upstream_model, ppas, sign_key):
        self.deb_model = deb_model
        self.name = self.deb_model.name
        self.upstream_model = upstream_model
        self.ppas = PPACollection(ppas)
        self.sign_key = sign_key

    @cached_property
    def missing_branches(self):
        """Returns any missing branches in our deb git repos that are defined upstream"""
        upstream_tags = self.upstream_model.tags_from_semver_point(
            enums.K8S_STARTING_SEMVER
        )
        deb_branches = self.deb_model.base.branches_from_semver_point(
            enums.K8S_STARTING_SEMVER
        )
        return list(set(upstream_tags) - set(deb_branches))

    @property
    def supported_versions(self):
        return list(enums.DEB_K8S_TRACK_MAP.keys())

    def sync_from_upstream(self):
        """Syncs branches from upstream tags"""
        if not self.missing_branches:
            self.log(f"All branches are synced, nothing to do here.")
            return

        with tempfile.TemporaryDirectory() as tmpdir:
            src_path = Path(tmpdir) / self.deb_model.src
            self.deb_model.base.clone(cwd=tmpdir)
            for branch in self.missing_branches:
                self.log(f"Processing branch {branch}")
                self.deb_model.base.checkout(branch, new_branch=True, cwd=str(src_path))

                changelog_fn = src_path / "debian/changelog"
                changelog_fn_tpl = src_path / "debian/changelog.in"

                k8s_major_minor = semver.VersionInfo.parse(branch.lstrip("v"))

                changelog_context = {
                    "deb_version": f"{str(k8s_major_minor)}-0",
                }

                self.log(f"Writing template vars {changelog_context}")
                changelog_out = changelog_fn_tpl.read_text()
                changelog_out = self.render(changelog_fn_tpl, changelog_context)
                changelog_fn.write_text(changelog_out)

                self.log(f"Committing {branch}")
                self.deb_model.base.add([str(changelog_fn)], cwd=str(src_path))
                self.deb_model.base.commit(
                    f"Creating branch {branch}", cwd=str(src_path)
                )
                self.deb_model.base.push(ref=branch, cwd=str(src_path))

    def sync_debs(self, force=False):
        """Builds latest deb from each major.minor and uploads to correct ppa"""
        for _version in self.supported_versions:
            exclude_pre = True
            if _version == enums.K8S_NEXT_VERSION:
                self.log(
                    f"Next development version triggered, will query pre-releases."
                )
                # Only pull in pre-releases if building for the next development version
                exclude_pre = False
            ppa = self.ppas.get_ppa_by_major_minor(_version)
            latest_deb_version = ppa.get_source_semver(self.deb_model.name)
            latest_deb_version_mmp = None
            if latest_deb_version:
                latest_deb_version_mmp = f"{latest_deb_version.major}.{latest_deb_version.minor}.{latest_deb_version.patch}"
            latest_branch_version = self.deb_model.base.latest_branch_from_major_minor(
                _version, exclude_pre
            )
            if (
                force
                or not latest_deb_version_mmp
                or semver.compare(str(latest_branch_version), latest_deb_version_mmp)
                > 0
            ):
                self.log(
                    f"Found new branch {str(latest_branch_version)} > {str(latest_deb_version_mmp)}, building new deb"
                )
                self.build(latest_branch_version)
                self.upload(enums.DEB_K8S_TRACK_MAP.get(_version))

            else:
                self.log(
                    f"> Versions match {str(latest_branch_version)} == {str(latest_deb_version_mmp)}, not building a new deb"
                )

    def render(self, tmpl_file, context):
        """Renders a jinja template with context"""
        template = Template(tmpl_file.read_text(), keep_trailing_newline=True)
        return template.render(context)

    def bump_revision(self, **subprocess_kwargs):
        """Bumps upstream revision for builds"""
        cmd_ok("dch -U 'Automated Build' -D focal", **subprocess_kwargs)

    def write_debversion(self, latest_branch_version, src_path):
        """Writes out the DEBVERSION file to be used in building the deps"""
        kube_git_version_fn = src_path / "DEBVERSION"
        kube_git_version = textwrap.dedent(
            """KUBE_GIT_TREE_STATE=archive
            KUBE_GIT_VERSION={}
            KUBE_GIT_MAJOR={}
            KUBE_GIT_MINOR={}
            """.format(
                f"v{str(latest_branch_version)}",
                latest_branch_version.major,
                latest_branch_version.minor,
            )
        )
        kube_git_version_fn.write_text(kube_git_version)

    def source(self, **subprocess_kwargs):
        """Builds the source deb package"""
        cmd = ["dpkg-buildpackage", "-S", f"--sign-key={self.sign_key}"]
        self.log(f"Building package: {cmd}")
        cmd_ok(cmd, **subprocess_kwargs)

    def cleanup_source(self, **subprocess_kwargs):
        cmd_ok("rm -rf *.changes", shell=True, **subprocess_kwargs)

    def cleanup_debian(self, **subprocess_kwargs):
        cmd_ok(["rm", "-rf", "debian"], **subprocess_kwargs)

    @sham
    def upload(self, ppa, **subprocess_kwargs):
        """Uploads source packages via dput"""
        for changes in list(Path(".").glob("*changes")):
            cmd = f"dput {ppa} {str(changes)}"
            self.log(cmd)
            cmd_ok(cmd, **subprocess_kwargs)
        self.cleanup_source()
        self.cleanup_debian(cwd=self.upstream_model.name)

    def build(self, latest_branch_version):
        """Builds the debian package for latest version"""
        self.upstream_model.clone()
        self.upstream_model.checkout(
            ref=f"tags/v{str(latest_branch_version)}",
            force=True,
            cwd=self.upstream_model.name,
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            self.log(f"Building {self.deb_model.name} debian package")
            self.deb_model.base.clone(cwd=tmpdir)
            self.deb_model.base.checkout(
                ref=f"v{str(latest_branch_version)}",
                force=True,
                cwd=f"{tmpdir}/{self.deb_model.name}",
            )
            self.bump_revision(cwd=f"{tmpdir}/{self.deb_model.name}")
            self.write_debversion(
                semver.VersionInfo.parse(latest_branch_version),
                src_path=Path(tmpdir) / self.deb_model.name,
            )
            cmd_ok(
                f"cp -a {tmpdir}/{self.deb_model.name}/* {self.upstream_model.name}/.",
                shell=True,
            )
            self.source(cwd=self.upstream_model.name)
            self.deb_model.base.add(
                ["debian/changelog"], cwd=f"{tmpdir}/{self.deb_model.name}"
            )
            self.deb_model.base.commit(
                "Automated Build", cwd=f"{tmpdir}/{self.deb_model.name}"
            )
            self.deb_model.base.push(
                ref=f"v{str(latest_branch_version)}",
                cwd=f"{tmpdir}/{self.deb_model.name}",
            )


class DebCNIService(DebService):
    """This is a separate service for container networking as it does not follow the normal kubernetes versioning scheme"""

    @cached_property
    def missing_branches(self):
        """Returns any missing branches in our deb git repos that are defined upstream"""
        upstream_tags = self.upstream_model.tags_from_semver_point("0.8.7")
        deb_branches = self.deb_model.base.branches_from_semver_point("0.8.7")
        return list(set(upstream_tags) - set(deb_branches))

    def sync_debs(self, force=False):
        """Builds latest deb from each major.minor and uploads to correct ppa"""
        for ppa_name in self.ppas.names:
            ppa = self.ppas.get_ppa_by_major_minor(ppa_name)
            exclude_pre = True
            latest_deb_version = ppa.get_source_semver(self.deb_model.name)
            latest_deb_version_mmp = (
                f"{latest_deb_version.major}.{latest_deb_version.minor}.{latest_deb_version.patch}"
                if latest_deb_version
                else None
            )
            latest_branch_version = self.deb_model.base.latest_branch_from_major_minor(
                enums.K8S_CNI_SEMVER, exclude_pre
            )
            if (
                force
                or not latest_deb_version
                or semver.compare(str(latest_branch_version), latest_deb_version_mmp)
                > 0
            ):
                self.log(
                    f"Found new branch {str(latest_branch_version)} > {str(latest_deb_version_mmp)}, building new deb"
                )
                self.build(latest_branch_version)
                self.upload(enums.DEB_K8S_TRACK_MAP.get(ppa_name))
            else:
                self.log(
                    f"> Versions match {str(latest_branch_version)} == {str(latest_deb_version_mmp)}, not building a new deb"
                )


class DebCriToolsService(DebService):
    """This is a separate service for cri-tools as it does not follow the normal kubernetes versioning scheme"""

    @cached_property
    def missing_branches(self):
        """Returns any missing branches in our deb git repos that are defined upstream"""
        upstream_tags = self.upstream_model.tags_from_semver_point("1.19.0")
        deb_branches = self.deb_model.base.branches_from_semver_point("1.19.0")
        return list(set(upstream_tags) - set(deb_branches))

    def sync_debs(self, force=False):
        """Builds latest deb from each major.minor and uploads to correct ppa"""
        for ppa_name in self.ppas.names:
            ppa = self.ppas.get_ppa_by_major_minor(ppa_name)
            exclude_pre = True
            latest_deb_version = ppa.get_source_semver(self.deb_model.name)
            latest_deb_version_mmp = (
                f"{latest_deb_version.major}.{latest_deb_version.minor}.{latest_deb_version.patch}"
                if latest_deb_version
                else None
            )
            latest_branch_version = self.deb_model.base.latest_branch_from_major_minor(
                enums.K8S_CRI_TOOLS_SEMVER, exclude_pre
            )
            if (
                force
                or not latest_deb_version
                or semver.compare(str(latest_branch_version), latest_deb_version_mmp)
                > 0
            ):
                self.log(
                    f"Found new branch {str(latest_branch_version)} > {str(latest_deb_version_mmp)}, building new deb"
                )
                self.build(latest_branch_version)
                self.upload(enums.DEB_K8S_TRACK_MAP.get(ppa_name))
            else:
                self.log(
                    f"> Versions match {str(latest_branch_version)} == {str(latest_deb_version_mmp)}, not building a new deb"
                )
