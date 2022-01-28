# -*- coding: utf-8 -*-
"""
charms.py - Interface to building and publishing charms.

Make sure that charm environments variables are set appropriately

CHARM_BUILD_DIR, CHARM_LAYERS_DIR, CHARM_INTERFACES_DIR

See `charm build --help` for more information.

Usage:

  tox -e py36 -- python3 jobs/build-charms/charms.py build \
     --charm-list jobs/includes/charm-support-matrix.inc \
     --resource-spec jobs/build-charms/resource-spec.yaml

  tox -e py36 -- python3 jobs/build-charms/charms.py --help
"""

import os
from io import BytesIO
import zipfile
from pathlib import Path
from sh.contrib import git
from cilib.git import default_gh_branch
from cilib.service.aws import Store
from cilib.run import cmd_ok, capture, script
from datetime import datetime
from enum import Enum
from retry.api import retry_call

from pathos.threading import ThreadPool
from pprint import pformat
import click
import shutil
import sh
import yaml
import json
import requests
import re


class BuildException(Exception):
    """Define build Exception."""


class BuildType(Enum):
    """Enumeration for the build type."""

    CHARM = 1
    BUNDLE = 2


class LayerType(Enum):
    """Enumeration for the layer type."""

    LAYER = 1
    INTERFACE = 2


def _next_match(seq, predicate=lambda _: _, default=None):
    """Finds the first item of an iterable matching a predicate, or default if none exists."""
    return next(filter(predicate, seq), default)


class _WrappedCmd:
    def __init__(self, entity, runner):
        self._echo = entity.echo
        self._run = runner

    def build(self, *args, **kwargs):
        try:
            ret = self._run.build(*args, **kwargs)
            assert not getattr(ret, "ok", None), "sh lib added an 'ok' attribute"
            ret.ok = True
        except sh.ErrorReturnCode as ret:
            assert not getattr(ret, "ok", None), "sh lib added an 'ok' attribute"
            ret.ok = False
            ret.cmd = ret.full_cmd
        return ret


class CharmCmd(_WrappedCmd):
    def __init__(self, entity):
        super().__init__(entity, sh.charm.bake(_tee=True, _out=entity.echo))
        self.charm = self._run


class CharmcraftCmd(_WrappedCmd):
    def __init__(self, entity):
        super().__init__(entity, sh.charmcraft.bake(_tee=True, _out=entity.echo))
        self.charmcraft = self._run


class _CharmStore(CharmCmd):
    def show(self, *args, **kwargs):
        return self.charm.show(*args, **kwargs)

    def id(self, charm_entity, channel):
        try:
            charm_id = self.show(charm_entity, "id", channel=channel)
        except sh.ErrorReturnCode:
            return None
        response = yaml.safe_load(charm_id.stdout.decode().strip())
        return response["id"]["Id"]

    def resources(self, charm_id, channel):
        try:
            resources = self.charm(
                "list-resources",
                charm_id,
                channel=channel,
                format="yaml",
            )
            return yaml.safe_load(resources.stdout.decode())
        except sh.ErrorReturnCode:
            return []

    def promote(self, charm_entity, from_channel, to_channel):
        self._echo(
            f"Promoting :: {charm_entity:^35} :: from: {from_channel} to: {to_channel}"
        )
        charm_id = self.id(charm_entity, from_channel)
        charm_resources = self.resources(charm_id, from_channel)
        if not charm_resources:
            self._echo("No resources for {}".format(charm_id))
        resources_args = [
            (
                "--resource",
                "{}-{}".format(resource["name"], resource["revision"]),
            )
            for resource in charm_resources
        ]
        self.charm.release(charm_id, f"--channel={to_channel}", *resources_args)
        return charm_id

    def grant(self, charm_id):
        self._echo(f"Setting   :: {charm_id:^35} :: permissions for read everyone")
        self.charm.grant(charm_id, "everyone", acl="read")

    def upload(self, dst_path, entity):
        out = self.charm.push(dst_path, entity)
        self._echo(f"Pushing   :: {entity:^35} :: returns {out.stdout or out.stderr}")

        # Output includes lots of ansi escape sequences from the docker push,
        # and we only care about the first line, which contains the url as yaml.
        out = yaml.safe_load(out.stdout.decode().strip().splitlines()[0])
        return out["url"]

    def set(self, entity, commit):
        self._echo(f"Setting {entity} metadata: {commit}")
        self.charm.set(entity, f"commit={commit}")

    def upload_resource(self, entity, resource_name, resource):
        # If the resource is a file, populate the path where it was built.
        # If it's a custom image, it will be in Docker and this will be a no-op.
        retry_call(
            self.charm.attach,
            fargs=[
                entity,
                f"{resource_name}={resource}",
            ],
            delay=2,
            backoff=2,
            tries=15,
            exceptions=sh.ErrorReturnCode,
        )


class _CharmHub(CharmcraftCmd):
    STATUS_RESOURCE = re.compile(r"(\S+) \(r(\d+)\)")

    @staticmethod
    def _table_to_list(header, body):
        if not body:
            return None
        rows = []
        titles = [title for title in re.split(r"\s{2,}", header) if title]
        for line in body:
            row, head = {}, line
            for key in reversed(titles):
                head, *value = head.strip().rsplit("  ", 1)
                head, value = (head, value[0]) if value else ("", head.strip())
                row[key] = value or rows[-1].get(key)
            rows.append(row)
        return rows

    @staticmethod
    def refresh(name, channel=None, architecture=None, base_channel=None):
        channel = channel or "stable"
        architecture = architecture or "amd64"
        base_channel = base_channel or "20.04"
        data = {
            "context": [],
            "actions": [
                {
                    "name": name,
                    "base": {
                        "name": "ubuntu",
                        "architecture": architecture,
                        "channel": base_channel,
                    },
                    "channel": channel,
                    "action": "install",
                    "instance-key": "charmed-kubernetes/build-charms",
                }
            ],
        }
        resp = requests.post("https://api.charmhub.io/v2/charms/refresh", json=data)
        return resp.json()

    def status(self, charm_entity):
        """Read CLI Table output from charmcraft status and parse."""
        charm_status = self.charmcraft.status(charm_entity)
        header, *body = charm_status.stdout.decode().splitlines()
        channel_status = self._table_to_list(header, body)

        for idx, row in enumerate(channel_status):
            resources = row.get("Resources", "")
            if resources == "-":
                row["Resources"] = []
            elif resources == "↑":
                row["Resources"] = channel_status[idx - 1]["Resources"]
            else:
                row["Resources"] = dict(self.STATUS_RESOURCE.findall(resources))
        return channel_status

    def revisions(self, charm_entity):
        """Read CLI Table output from charmcraft revisions and parse."""
        charm_status = self.charmcraft.revisions(charm_entity)
        header, *body = charm_status.stdout.decode().splitlines()
        return self._table_to_list(header, body)

    def resources(self, charm_entity):
        """Read CLI Table output from charmcraft resources and parse."""
        charmcraft_out = self.charmcraft.resources(charm_entity)
        header, *body = charmcraft_out.stdout.decode().splitlines()
        return self._table_to_list(header, body)

    def resource_revisions(self, charm_entity, resource):
        """Read CLI Table output from charmcraft resource-revisions and parse."""
        charmcraft_out = self.charmcraft("resource-revisions", charm_entity, resource)
        header, *body = charmcraft_out.stdout.decode().splitlines()
        return self._table_to_list(header, body)

    def _unpublished_revisions(self, charm_entity):
        """
        Get the most recent non-released version.

        It is possible no unreleased charm exists.
        It is possible multiple unreleased versions exist since the last released one
        We want ONLY the most recent of that list

        This also gathers the most recently published resource, whether
        it is associated with a particular prior release or not.
        """
        charm_status = []
        unpublished_rev = _next_match(
            self.revisions(charm_entity),
            predicate=lambda rev: rev["Status"] != "released",
        )
        if unpublished_rev:
            charm_resources = [
                rsc
                for rsc in self.resources(charm_entity)
                if rsc["Charm Rev"] == unpublished_rev["Revision"]
            ]
            unpublished_rev["Resources"] = {
                resource["Resource"]: _next_match(
                    self.resource_revisions(charm_entity, resource["Resource"]),
                    default=dict(),
                ).get("Revision")
                for resource in charm_resources
            }
            charm_status = [unpublished_rev]
        return charm_status

    def promote(self, charm_entity, from_channel, to_channel):
        self._echo(
            f"Promoting :: {charm_entity:^35} :: from:{from_channel} to: {to_channel}"
        )
        if from_channel == "unpublished":
            charm_status = self._unpublished_revisions(charm_entity)
        else:
            charm_status = [
                row
                for row in self.status(charm_entity)
                if f"{row['Track']}/{row['Channel']}" == from_channel
            ]

        calls = set()
        for row in charm_status:
            revision, resources = row["Revision"], row["Resources"]
            resource_args = (
                f"--resource={name}:{rev}" for name, rev in resources.items() if rev
            )
            calls.add(
                (
                    charm_entity,
                    f"--revision={revision}",
                    f"--channel={to_channel}",
                    *resource_args,
                )
            )
        for args in calls:
            self.charmcraft.release(*args)

    def upload(self, dst_path):
        out = self.charmcraft.upload("-q", dst_path)
        (revision,) = re.findall(
            r"^Revision (\d+) of ", out.stdout.decode(), re.MULTILINE
        )
        self._echo(f"Pushing   :: returns {out.stdout or out.stderr}")
        return revision

    def upload_resource(self, charm_entity, resource_name, resource):
        kwargs = dict([resource])
        self.charmcraft("upload-resource", charm_entity, resource_name, **kwargs)


class BuildEnv:
    """Charm or Bundle build data class."""

    REV = re.compile("rev: ([a-zA-Z0-9]+)")

    def __new__(cls, *args, **kwargs):
        """Initialize class variables used during the build from the CI environment."""
        try:
            cls.build_dir = Path(os.environ.get("CHARM_BUILD_DIR"))
            cls.layers_dir = Path(os.environ.get("CHARM_LAYERS_DIR"))
            cls.interfaces_dir = Path(os.environ.get("CHARM_INTERFACES_DIR"))
            cls.charms_dir = Path(os.environ.get("CHARM_CHARMS_DIR"))
            cls.work_dir = Path(os.environ.get("WORKSPACE"))
            cls.tmp_dir = cls.work_dir / "tmp"
            cls.home_dir = Path(os.environ.get("HOME"))
        except TypeError:
            raise BuildException(
                "CHARM_BUILD_DIR, CHARM_LAYERS_DIR, CHARM_INTERFACES_DIR, WORKSPACE, HOME: "
                "Unable to find some or all of these charm build environment variables."
            )
        return super(BuildEnv, cls).__new__(cls)

    def __init__(self, build_type):
        """Create a BuildEnv to hold/save build metadata."""
        self.store = Store("BuildCharms")
        self.now = datetime.utcnow()
        self.build_type = build_type
        self.db = {}
        self.clean_dirs = tuple()

        if self.build_type == BuildType.CHARM:
            self.db_json = Path("buildcharms.json")
            self.repos_dir = None
            self.clean_dirs = (self.layers_dir, self.interfaces_dir, self.charms_dir)

        elif self.build_type == BuildType.BUNDLE:
            self.db_json = Path("buildbundles.json")
            self.repos_dir = self.tmp_dir / "repos"
            self.bundles_dir = self.tmp_dir / "bundles"
            self.default_repo_dir = self.repos_dir / "bundles-kubernetes"
            self.clean_dirs = (self.repos_dir, self.bundles_dir)

        if not self.db.get("build_datetime", None):
            self.db["build_datetime"] = self.now.strftime("%Y/%m/%d")

        # Reload data from current day
        response = self.store.get_item(
            Key={"build_datetime": self.db["build_datetime"]}
        )
        if response and "Item" in response:
            self.db = response["Item"]

    def clean(self):
        for each in self.clean_dirs:
            if each.exists():
                shutil.rmtree(each)
            each.mkdir(parents=True)

    @property
    def layers(self):
        """List of layers defined in our jobs/includes/charm-layer-list.inc."""
        return yaml.safe_load(
            Path(self.db["build_args"]["layer_list"]).read_text(encoding="utf8")
        )

    @property
    def artifacts(self):
        """List of charms or bundles to process."""
        return yaml.safe_load(
            Path(self.db["build_args"]["artifact_list"]).read_text(encoding="utf8")
        )

    @property
    def layer_index(self):
        """Remote Layer index."""
        return self.db["build_args"].get("layer_index", None)

    @property
    def layer_branch(self):
        """Remote Layer branch."""
        return self.db["build_args"].get("layer_branch", None)

    @property
    def filter_by_tag(self):
        """Filter by tag."""
        return self.db["build_args"].get("filter_by_tag", None)

    @property
    def resource_spec(self):
        """Get Resource specs."""
        return self.db["build_args"].get("resource_spec", None)

    @property
    def to_channel(self):
        """Get destination channel."""
        return self.db["build_args"].get("to_channel", None)

    @property
    def from_channel(self):
        """Get source channel."""
        return self.db["build_args"].get("from_channel", None)

    @property
    def force(self):
        """Get if we should force a build."""
        return self.db["build_args"].get("force", None)

    def echo(self, msg):
        """Click echo wrapper."""
        click.echo(f"[BuildEnv] {msg}")

    def save(self):
        """Store build metadata into stateful db."""
        self.echo("Saving build")
        self.echo(dict(self.db))
        self.db_json.write_text(json.dumps(dict(self.db)))
        self.store.put_item(Item=dict(self.db))

    def promote_all(self, from_channel="unpublished", to_channel="edge", store="cs"):
        """Promote set of charm artifacts in the store."""
        for charm_map in self.artifacts:
            for charm_name, charm_opts in charm_map.items():
                if not any(match in self.filter_by_tag for match in charm_opts["tags"]):
                    continue
                cs_store = charm_opts.get("store") or store
                if cs_store == "cs":
                    charm_entity = f"cs:~{charm_opts['namespace']}/{charm_name}"
                    _CharmStore(self).promote(charm_entity, from_channel, to_channel)
                elif cs_store == "ch":
                    _CharmHub(self).promote(charm_name, from_channel, to_channel)

    def download(self, layer_name):
        """Pull layer source from the charm store."""
        out = capture(
            f"charm pull-source -i {self.layer_index} -b {self.layer_branch} {layer_name}"
        )
        self.echo(f"-  {out.stdout.decode()}")
        layer_manifest = {
            "rev": self.REV.search(out.stdout.decode()).group(1),
            "url": layer_name,
        }
        return layer_manifest

    def pull_layers(self):
        """Clone all downstream layers to be processed locally when doing charm builds."""
        layers_to_pull = []
        for layer_map in self.layers:
            layer_name = list(layer_map.keys())[0]

            if layer_name == "layer:index":
                continue

            layers_to_pull.append(layer_name)

        pool = ThreadPool()
        results = pool.map(self.download, layers_to_pull)

        self.db["pull_layer_manifest"] = [result for result in results]


class BuildEntity:
    """The Build data class."""

    def __init__(self, build, name, opts, default_store):
        """
        Represent a charm or bundle which should be built and published.

        @param BuildEnv build:
        @param str name: Name of the charm
        @param dict[str,str] opts:
        @param str default_store:
        """
        # Build env
        self.build = build

        # Bundle or charm name
        self.name = name
        self.type = "Charm"

        if build.repos_dir:
            self.checkout_path = build.repos_dir / opts.get("sub-repo", "")
        else:
            self.checkout_path = build.charms_dir / self.name

        src_path = self.checkout_path / opts.get("subdir", "")

        downstream = opts.get("downstream")
        branch = opts.get("branch")

        if not branch and downstream:
            # if branch not specified, use repo's default branch
            auth = os.environ.get("CDKBOT_GH_USR"), os.environ.get("CDKBOT_GH_PSW")
            branch = default_gh_branch(downstream, ignore_errors=True, auth=auth)

        if not branch:
            # if branch not specified, use the build_args branch
            branch = self.build.db["build_args"].get("branch")

        self.branch = branch or "master"

        self.layer_path = src_path / "layer.yaml"
        self.legacy_charm = False

        self.src_path = str(src_path.absolute())
        self.dst_path = str(self.build.build_dir / self.name)

        # Bundle or charm opts as defined in the layer include
        self.opts = opts

        self.namespace = opts["namespace"]

        self.store = opts.get("store") or default_store
        if self.store == "cs":
            # Entity path, ie. cs:~containers/kubernetes-worker
            self.entity = f"cs:~{opts['namespace']}/{name}"
        elif self.store == "ch":
            # Entity path, ie. kubernetes-worker
            self.entity = name
        else:
            raise BuildException(f"'{self.store}' doesn't exist")

        # Entity path with current revision (from target channel)
        self.full_entity = self._get_full_entity()

        # Entity path with new revision (from pushing)
        self.new_entity = None

    def __str__(self):
        """Represent build entity as a string."""
        return f"<BuildEntity: {self.name} ({self.full_entity}) (legacy charm: {self.legacy_charm})>"

    def echo(self, msg):
        """Click echo wrapper."""
        click.echo(f"[{self.name}] {msg}")

    def _get_full_entity(self):
        """Grab identifying revision for charm's channel."""
        if self.store == "cs":
            return _CharmStore(self).id(
                self.entity, self.build.db["build_args"]["to_channel"]
            )
        else:
            return f'{self.entity}:{self.build.db["build_args"]["to_channel"]}'

    def download(self, fname):
        """Fetch single file from associated store/charm/channel."""
        if not self.full_entity:
            return None
        elif self.store == "cs":
            entity_p = self.full_entity.lstrip("cs:")
            url = f"https://api.jujucharms.com/charmstore/v5/{entity_p}/archive/{fname}"
            self.echo(f"Downloading {fname} from {url}")
            resp = requests.get(url)
            if resp.ok:
                return yaml.safe_load(resp.content.decode())
        elif self.store == "ch":
            name, channel = self.full_entity.rsplit(":")
            refreshed = _CharmHub.refresh(name, channel)
            try:
                url = refreshed["results"][0]["charm"]["download"]["url"]
            except (KeyError, TypeError):
                self.echo(f"Failed to find in charmhub.io \n{refreshed}")
                return None
            resp = requests.get(url, stream=True)
            if resp.ok:
                yaml_file = zipfile.Path(BytesIO(resp.content)) / fname
                return yaml.safe_load(yaml_file.read_text())

    @property
    def has_changed(self):
        """Determine if the charm/layers commits have changed since last publish to charmstore."""
        if not self.legacy_charm and self.store == "cs":
            # Operator framework charms won't have a .build.manifest and it's
            # sufficient to just compare the charm repo's commit rev.
            cs = _CharmStore(self)
            try:
                extra_info = yaml.safe_load(
                    cs.show(
                        self.full_entity,
                        "extra-info",
                        format="yaml",
                    ).stdout.decode()
                )["extra-info"]
                old_commit = extra_info.get("commit")
                new_commit = self.commit
                changed = new_commit != old_commit
            except sh.ErrorReturnCode:
                changed = True
                old_commit = None
                new_commit = None
            if changed:
                self.echo(f"Changes found: {new_commit} (new) != {old_commit} (old)")
            else:
                self.echo(f"No changes found: {new_commit} (new) == {old_commit} (old)")
            return changed

        charmstore_build_manifest = self.download(".build.manifest")

        if not charmstore_build_manifest:
            self.echo(
                "No build.manifest located, unable to determine if any changes occurred."
            )
            return True

        comparisons = ["rev", "url"]
        current_build_manifest = [
            {k: curr[k] for k in comparisons}
            for curr in self.build.db["pull_layer_manifest"]
        ]

        # Check the current git cloned charm repo commit and add that to
        # current pull-layer-manifest as that would not be known at the
        # time of pull_layers
        current_build_manifest.append({"rev": self.commit, "url": self.name})

        the_diff = [
            i
            for i in charmstore_build_manifest["layers"]
            if {k: i[k] for k in comparisons} not in current_build_manifest
        ]
        if the_diff:
            self.echo("Changes found:")
            self.echo(the_diff)
            return True
        self.echo(f"No changes found, not building a new {self.entity}")
        return False

    @property
    def commit(self):
        """Commit hash of downstream repo."""
        if not Path(self.src_path).exists():
            raise BuildException(f"Could not locate {self.src_path}")

        git_commit = git("rev-parse", "HEAD", _cwd=self.src_path)
        return git_commit.stdout.decode().strip()

    def _read_metadata_resources(self):
        if not self.legacy_charm:
            metadata_path = Path(self.src_path) / "metadata.yaml"
        elif self.dst_path.endswith("charm"):
            metadata_path = zipfile.Path(self.dst_path) / "metadata.yaml"
        else:
            # Legacy (reactive) charms can have resources added by layers,
            # so we need to read from the built charm.
            metadata_path = Path(self.dst_path) / "metadata.yaml"
        metadata = yaml.safe_load(metadata_path.read_text())
        return metadata.get("resources", {})

    def setup(self):
        """Set up directory for charm build."""
        downstream = f"https://github.com/{self.opts['downstream']}"
        self.echo(f"Cloning repo from {downstream} branch {self.branch}")

        os.makedirs(self.checkout_path)
        ret = cmd_ok(
            f"git clone --branch {self.branch} {downstream} {self.checkout_path}",
            echo=self.echo,
        )
        if not ret.ok:
            raise SystemExit("Clone failed")

        self.legacy_charm = self.layer_path.exists()
        if not self.legacy_charm and self.type == "charm":
            self.dst_path += ".charm"

    def charm_build(self):
        """Perform a build against charm/bundle."""
        if "override-build" in self.opts:
            self.echo("Override build found, running in place of charm build.")
            ret = script(
                self.opts["override-build"],
                cwd=self.src_path,
                charm=self.name,
                echo=self.echo,
            )
        elif self.legacy_charm:
            args = "-r --force -i https://localhost"
            if self.store == "ch":
                args += " --charm-file"
                self.dst_path = str(Path(self.src_path) / f"{self.name}.charm")
            self.echo(f"Building with: charm build {args}")
            ret = CharmCmd(self).build(*args.split(), _cwd=self.src_path)
        else:
            args = f"-f {self.src_path}"
            self.echo(f"Building with: charmcraft build {args}")
            ret = CharmcraftCmd(self).build(*args.split(), _cwd=self.build.build_dir)
        if not ret.ok:
            self.echo("Failed to build, aborting")
            raise SystemExit(f"Failed to build {self.name}")

    def push(self):
        """Pushes a built charm to Charm store/hub."""
        if "override-push" in self.opts:
            self.echo("Override push found, running in place of charm push.")
            script(
                self.opts["override-push"],
                cwd=self.src_path,
                charm=self.name,
                namespace=self.namespace,
                echo=self.echo,
            )
            return

        self.echo(
            f"Pushing {self.type}({self.name}) from {self.dst_path} to {self.entity}"
        )
        if self.store == "cs":
            cs = _CharmStore(self)
            self.new_entity = cs.upload(self.dst_path, self.entity)
            cs.set(self.new_entity, self.commit)
        elif self.store == "ch":
            self.new_entity = _CharmHub(self).upload(self.dst_path)

    def attach_resources(self):
        """Assemble charm's resources and associate in the store."""
        out_path = Path(self.src_path) / "tmp"
        os.makedirs(str(out_path), exist_ok=True)
        resource_spec = yaml.safe_load(Path(self.build.resource_spec).read_text())
        resource_spec = resource_spec.get(self.name, {})

        # Build any custom resources.
        resource_builder = self.opts.get("build-resources", None)
        if resource_builder and not resource_spec:
            raise SystemExit(
                f"Custom build-resources specified for {self.name} but no spec found"
            )
        if resource_builder:
            resource_builder = resource_builder.format(
                out_path=out_path,
                src_path=self.src_path,
            )
            self.echo("Running custom build-resources")
            ret = script(resource_builder, echo=self.echo)
            if not ret.ok:
                raise SystemExit("Failed to build custom resources")

        for name, details in self._read_metadata_resources().items():
            resource_fmt = resource_spec.get(name)
            if not resource_fmt:
                # ignore pushing a resource not defined in `resource_spec`
                continue
            if details["type"] == "oci-image":
                upstream_source = details.get("upstream-source")
                if upstream_source:
                    # Pull any `upstream-image` annotated resources.
                    self.echo(f"Pulling {upstream_source}...")
                    sh.docker.pull(upstream_source)
                    resource_fmt = upstream_source
                resource_spec[name] = ("image", resource_fmt)
            elif details["type"] == "file":
                resource_spec[name] = (
                    "filepath",
                    resource_fmt.format(out_path=out_path),
                )

        self.echo(f"Attaching resources:\n{pformat(resource_spec)}")
        # Attach all resources.
        for resource_name, resource in resource_spec.items():
            if self.store == "cs":
                _CharmStore(self).upload_resource(
                    self.new_entity, resource_name, resource[1]
                )
            elif self.store == "ch":
                _CharmHub(self).upload_resource(self.entity, resource_name, resource)

    def promote(self, from_channel="unpublished", to_channel="edge"):
        """Promote charm and its resources from a channel to another."""
        if self.store == "cs":
            cs = _CharmStore(self)
            charm_id = cs.promote(self.entity, from_channel, to_channel)
            cs.grant(charm_id)
        elif self.store == "ch":
            if to_channel == "edge" and from_channel == "unpublished":
                track = self.build.db["build_args"].get("track") or "latest"
                to_channel = f"{track}/edge"
            _CharmHub(self).promote(self.entity, from_channel, to_channel)


class BundleBuildEntity(BuildEntity):
    """Overrides BuildEntity with bundle specific methods."""

    def __init__(self, *args, **kwargs):
        """Create a BuildEntity for Charm Bundles."""
        super().__init__(*args, **kwargs)
        self.type = "Bundle"
        self.src_path = str(self.opts["src_path"])
        self.dst_path = str(self.opts["dst_path"])

    @property
    def has_changed(self):
        """Determine if this bundle has changes to include in a new push."""
        charmstore_bundle = self.download("bundle.yaml")

        local_built_bundle = yaml.safe_load(
            (Path(self.dst_path) / "bundle.yaml").read_text(encoding="utf8")
        )

        if charmstore_bundle != local_built_bundle:
            self.echo("Local bundle differs.")
            return True

        self.echo(f"No differences found, not pushing new bundle {self.entity}")
        return False

    def bundle_build(self, to_channel):
        if not self.opts.get("skip-build"):
            cmd = f"{self.src_path}/bundle -o {self.dst_path} -c {to_channel} {self.opts['fragments']}"
            self.echo(f"Running {cmd}")
            cmd_ok(cmd, echo=self.echo)
        else:
            # If we're not building the bundle from the repo, we have
            # to copy it to the expected output location instead.
            shutil.copytree(
                Path(self.src_path) / self.opts.get("subdir", ""), self.dst_path
            )


@click.group()
def cli():
    """Define click group."""


@cli.command()
@click.option(
    "--charm-list", required=True, help="path to a file with list of charms in YAML"
)
@click.option("--layer-list", required=True, help="list of layers in YAML format")
@click.option("--layer-index", required=True, help="Charm layer index")
@click.option(
    "--charm-branch",
    required=True,
    help="Git branch to build charm from",
    default="master",
)
@click.option(
    "--layer-branch",
    required=True,
    help="Git branch to pull layers/interfaces from",
    default="master",
)
@click.option(
    "--resource-spec", required=True, help="YAML Spec of resource keys and filenames"
)
@click.option(
    "--filter-by-tag",
    required=True,
    help="only build for charms matching a tag, comma separate list",
    multiple=True,
)
@click.option(
    "--track", required=True, help="track to promote charm to", default="latest"
)
@click.option(
    "--to-channel", required=True, help="channel to promote charm to", default="edge"
)
@click.option(
    "--store",
    type=click.Choice(["cs", "ch"], case_sensitive=False),
    help="Publish to Charmstore (cs) or Charmhub (ch) if the resource-spec doesn't specify.",
    default="cs",
)
@click.option("--force", is_flag=True)
def build(
    charm_list,
    layer_list,
    layer_index,
    charm_branch,
    layer_branch,
    resource_spec,
    filter_by_tag,
    track,
    to_channel,
    store,
    force,
):
    """Build a set of charms and publish with their resources."""
    cmd_ok("which charm", echo=lambda m: click.echo(f"charm -> {m}"))
    cmd_ok("which charmcraft", echo=lambda m: click.echo(f"charmcraft -> {m}"))

    build_env = BuildEnv(build_type=BuildType.CHARM)
    build_env.db["build_args"] = {
        "artifact_list": charm_list,
        "layer_list": layer_list,
        "layer_index": layer_index,
        "branch": charm_branch,
        "layer_branch": layer_branch,
        "resource_spec": resource_spec,
        "filter_by_tag": list(filter_by_tag),
        "track": track,
        "to_channel": to_channel,
        "force": force,
    }
    build_env.clean()
    build_env.pull_layers()

    entities = []
    for charm_map in build_env.artifacts:
        for charm_name, charm_opts in charm_map.items():
            if not any(match in filter_by_tag for match in charm_opts["tags"]):
                continue

            charm_entity = BuildEntity(build_env, charm_name, charm_opts, store)
            entities.append(charm_entity)
            click.echo(f"Queued {charm_entity.entity} for building")

    for entity in entities:
        entity.echo("Starting")
        try:
            entity.setup()
            entity.echo(f"Details: {entity}")

            if not entity.has_changed and not build_env.force:
                continue

            entity.charm_build()

            entity.push()
            entity.attach_resources()
            entity.promote(to_channel=to_channel)
        finally:
            entity.echo("Stopping")

    build_env.save()


@cli.command()
@click.option("--bundle-list", required=True, help="list of bundles in YAML format")
@click.option(
    "--bundle-branch",
    default="master",
    required=True,
    help="Upstream branch to build bundles from",
)
@click.option(
    "--filter-by-tag",
    required=True,
    help="only build for charms matching a tag, comma separate list",
    multiple=True,
)
@click.option(
    "--bundle-repo",
    required=True,
    help="upstream repo for bundle builder",
    default="https://github.com/charmed-kubernetes/bundle-canonical-kubernetes.git",
)
@click.option(
    "--track", required=True, help="track to promote charm to", default="latest"
)
@click.option(
    "--to-channel", required=True, help="channel to promote bundle to", default="edge"
)
@click.option(
    "--store",
    type=click.Choice(["cs", "ch"], case_sensitive=False),
    help="Charmstore (cs) or Charmhub (ch)",
    default="cs",
)
def build_bundles(
    bundle_list, bundle_branch, filter_by_tag, bundle_repo, track, to_channel, store
):
    """Build list of bundles from a specific branch according to filters."""
    build_env = BuildEnv(build_type=BuildType.BUNDLE)
    build_env.db["build_args"] = {
        "artifact_list": bundle_list,
        "branch": bundle_branch,
        "filter_by_tag": list(filter_by_tag),
        "track": track,
        "to_channel": to_channel,
    }

    build_env.clean()
    default_repo_dir = build_env.default_repo_dir
    cmd_ok(f"git clone --branch {bundle_branch} {bundle_repo} {default_repo_dir}")

    entities = []
    for bundle_map in build_env.artifacts:
        for bundle_name, bundle_opts in bundle_map.items():
            if not any(match in filter_by_tag for match in bundle_opts["tags"]):
                continue
            if "downstream" in bundle_opts:
                bundle_opts["sub-repo"] = bundle_name
                bundle_opts["src_path"] = build_env.repos_dir / bundle_name
            else:
                bundle_opts["src_path"] = build_env.default_repo_dir
            bundle_opts["dst_path"] = build_env.bundles_dir / bundle_name

            build_entity = BundleBuildEntity(build_env, bundle_name, bundle_opts, store)
            entities.append(build_entity)

    for entity in entities:
        entity.echo("Starting")

        try:
            if "downstream" in entity.opts:
                # clone bundle repo override
                entity.setup()
            entity.echo(f"Details: {entity}")
            entity.bundle_build(to_channel)
            entity.push()
            entity.promote(to_channel=to_channel)
        finally:
            entity.echo("Stopping")

    build_env.save()


@cli.command()
@click.option("--charm-list", required=True, help="path to charm list YAML")
@click.option(
    "--filter-by-tag",
    required=True,
    help="only build for charms matching a tag, comma separate list",
    multiple=True,
)
@click.option(
    "--from-channel",
    default="unpublished",
    required=True,
    help="Charm channel to publish from",
)
@click.option("--to-channel", required=True, help="Charm channel to publish to")
@click.option(
    "--store",
    type=click.Choice(["cs", "ch"], case_sensitive=False),
    help="Charmstore (cs) or Charmhub (ch)",
    default="cs",
)
def promote(charm_list, filter_by_tag, from_channel, to_channel, store):
    """
    Promote channel for a set of charms filtered by tag.
    """
    build_env = BuildEnv(build_type=BuildType.CHARM)
    build_env.db["build_args"] = {
        "artifact_list": charm_list,
        "filter_by_tag": list(filter_by_tag),
        "to_channel": to_channel,
        "from_channel": from_channel,
    }
    build_env.clean()
    return build_env.promote_all(
        from_channel=from_channel, to_channel=to_channel, store=store
    )


if __name__ == "__main__":
    cli()
