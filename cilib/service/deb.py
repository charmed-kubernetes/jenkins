"""Debian service object


Handles the building, syncing of debian packages
"""

import os
import tempfile
import semver
from jinja2 import Template
from pathlib import Path
from pymacaroons import Macaroon
from cilib import lp, idm, enums
from cilib.models.ppa import PPACollection
from cilib.run import cmd_ok
from cilib.log import DebugMixin
from drypy.patterns import sham


class DebService(DebugMixin):
    def __init__(self, deb_model, upstream_model, ppas):
        self.deb_model = deb_model
        self.name = self.deb_model.name
        self.upstream_model = upstream_model
        self.ppas = PPACollection(ppas)

    @property
    def missing_branches(self):
        """Returns any missing branches in our deb git repos that are defined upstream"""
        upstream_tags = self.upstream_model.tags_from_semver_point(
            enums.K8S_STARTING_SEMVER
        )
        deb_branches = self.deb_model.base.branches_from_semver_point(
            enums.K8S_STARTING_SEMVER
        )
        return list(set(upstream_tags) - set(deb_branches))

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

    def sync_debs(self, sign_key):
        """ Builds latest deb from each major.minor and uploads to correct ppa"""
        supported_versions = list(enums.DEB_K8S_TRACK_MAP.keys())
        for _version in supported_versions:
            self.deb_model.version = _version
            exclude_pre = True
            if _version == enums.K8S_NEXT_VERSION:
                self.log(
                    f"Next development version triggered, will query pre-releases."
                )
                # Only pull in pre-releases if building for the next development version
                exclude_pre = False
            ppa = self.ppas.get_ppa_by_major_minor(_version)
            latest_deb_version = ppa.get_source_semver(self.deb_model.name)
            latest_branch_version = self.deb_model.base.latest_branch_from_major_minor(
                _version, exclude_pre
            )
            if semver.compare(str(latest_branch_version), str(latest_deb_version)) > 0:
                self.log(
                    f"Found new branch {str(latest_branch_version)} > {str(latest_deb_version)}, building new deb"
                )
                self.upstream_model.clone()
                self.upstream_model.checkout(cwd=self.upstream_model.name)
                with tempfile.TemporaryDirectory() as tmpdir:
                    click.echo(f"Building {self.deb_model.name} debian package")
                    self.deb_model.base.clone(cwd=tmpdir)
                    self.deb_model.base.checkout(cwd=f"{tmpdir}/{self.deb_model.name}")
                self.bump_revision(cwd=f"{tmpdir}/{self.deb_model.name}")
                run(
                    f"cp -a {tmpdir}/{self.deb_model.name}/* {self.upstream_model.name}/.",
                    shell=True,
                )
                self.source(sign_key, include_source, cwd=self.upstream_model.name)
                self.deb_model.base.commit(
                    "Automated Build", cwd=f"{tmpdir}/{self.deb_model.name}"
                )
                self.deb_model.base.push(cwd=f"{tmpdir}/{self.deb_model.name}")
                self.upload(enums.DEB_K8S_TRACK_MAP.get(_version))
                self.cleanup_source()
                self.cleanup_debian(cwd=self.upstream_model.name)

            else:
                self.log(
                    f"> Versions match {str(latest_branch_version)} == {str(latest_deb_version)}, not building a new deb"
                )

    def render(self, tmpl_file, context):
        """Renders a jinja template with context"""
        template = Template(tmpl_file.read_text(), keep_trailing_newline=True)
        return template.render(context)

    def bump_revision(self, **subprocess_kwargs):
        """Bumps upstream revision for builds"""
        cmd_ok("dch -U 'Automated Build' -D focal", **subprocess_kwargs)

    def source(self, sign_key, **subprocess_kwargs):
        """Builds the source deb package"""
        cmd = ["dpkg-buildpackage", "-S", f"--sign-key={sign_key}"]
        click.echo(f"Building package: {cmd}")
        run(cmd, **subprocess_kwargs)

    def cleanup_source(self, **subprocess_kwargs):
        run("rm -rf *.changes", shell=True, **subprocess_kwargs)

    def cleanup_debian(self, **subprocess_kwargs):
        run(["rm", "-rf", "debian"], **subprocess_kwargs)

    @sham
    def upload(self, ppa, **subprocess_kwargs):
        """Uploads source packages via dput"""
        click.echo("Performing upload")
        for changes in list(Path(".").glob("*changes")):
            cmd_ok(f"dput {ppa} {str(changes)}", **subprocess_kwargs)

    # private


class DebCNIService(DebService):
    """This is a separate service for container networking as it does not follow the normal kubernetes versioning scheme"""

    @property
    def missing_branches(self):
        """Returns any missing branches in our deb git repos that are defined upstream"""
        upstream_tags = self.upstream_model.tags_from_semver_point("0.8.7")
        deb_branches = self.deb_model.base.branches_from_semver_point("0.8.7")
        return list(set(upstream_tags) - set(deb_branches))
