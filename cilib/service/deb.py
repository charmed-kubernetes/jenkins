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
        self.upstream_model = upstream_model

    @property
    def missing_branches(self):
        """Returns any missing branches in our snap git repos that are defined upstream"""
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
                    "deb_version": branch.lstrip("v"),
                }

                self.log(f"Writing template vars {changelog_context}")
                changelog_out = changelog_fn_tpl.read_text()
                changelog_out = self.render(changelog_fn_tpl, changelog_context)
                changelog_fn.write_text(changelog_yml)

                self.log(f"Committing {branch}")
                self.deb_model.base.add([str(changelog_fn)], cwd=str(src_path))
                self.deb_model.base.commit(
                    f"Creating branch {branch}", cwd=str(src_path)
                )
                self.deb_model.base.push(ref=branch, cwd=str(src_path))

    def render(self, tmpl_file, context):
        """Renders a jinja template with context"""
        template = Template(tmpl_file.read_text(), keep_trailing_newline=True)
        return template.render(context)

    # private
