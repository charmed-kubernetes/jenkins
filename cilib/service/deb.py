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
from cilib.run import cmd_ok
from cilib.log import DebugMixin
from drypy.patterns import sham


class DebService(DebugMixin):
    def __init__(self, deb_model, upstream_model):
        self.deb_model = deb_model
        self.name = self.deb_model.name
        self.upstream_model = upstream_model

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

        for branch in self.missing_branches:
            self.log(f"Processing branch {branch}")
            with tempfile.TemporaryDirectory() as tmpdir:
                src_path = Path(tmpdir) / self.deb_model.src
                self.deb_model.base.clone(cwd=tmpdir)
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

    def sync_all_debs(self):
        """ Builds latest debs from each major.minor and uploads to correct ppa"""
        supported_versions = list(enums.DEB_K8S_TRACK_MAP.keys())

    def render(self, tmpl_file, context):
        """Renders a jinja template with context"""
        template = Template(tmpl_file.read_text(), keep_trailing_newline=True)
        return template.render(context)

    def bump_revision(self, **subprocess_kwargs):
        """Bumps upstream revision for builds"""
        cmd_ok("dch -U 'Automated Build' -D focal", **subprocess_kwargs)

    def source(self, sign_key, include_source=False, **subprocess_kwargs):
        """Builds the source deb package"""
        cmd = ["dpkg-buildpackage", "-S", f"--sign-key={sign_key}"]
        if not include_source:
            cmd.append("-sd")
        click.echo(f"Building package: {cmd}")
        run(cmd, **subprocess_kwargs)

    def cleanup_source(self, **subprocess_kwargs):
        run("rm -rf *.changes", shell=True, **subprocess_kwargs)

    def cleanup_debian(self, **subprocess_kwargs):
        run(["rm", "-rf", "debian"], **subprocess_kwargs)

    def upload(self, ppa, **subprocess_kwargs):
        """Uploads source packages via dput"""
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
