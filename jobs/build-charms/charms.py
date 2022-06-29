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
import traceback
from io import BytesIO
import zipfile
from pathlib import Path
from sh.contrib import git
from cilib.git import default_gh_branch
from cilib.enums import SNAP_K8S_TRACK_MAP
from cilib.service.aws import Store
from cilib.run import cmd_ok, capture, script
from datetime import datetime
from dataclasses import dataclass
from enum import Enum
from types import SimpleNamespace
from typing import List, Mapping, Optional, Union

from pathos.threading import ThreadPool
from pprint import pformat
import click
import shutil
import sh
import yaml
import json
import requests
import re


RISKS = ["stable", "candidate", "beta", "edge"]


@dataclass
class Release:
    """Representation of Charm or Snap Release version."""

    major: int
    minor: int
    risk: Optional[str]

    def __str__(self):
        risk = ""
        if self.risk:
            risk = f"/{self.risk}" if self.risk.lower() in RISKS else ""
        return f"{self.major}.{self.minor}{risk}"

    def _as_cmp(self):
        return (
            self.major,
            self.minor,
            RISKS[::-1].index(self.risk.lower()) + 1 if self.risk else 0,
        )

    @classmethod
    def mk(cls, rel: str) -> "Release":
        has_risk = rel.split("/")
        if len(has_risk) == 2:
            track, risk = has_risk
        else:
            track, risk = has_risk[0], None
        return cls(*map(int, track.split(".")), risk)

    def __eq__(self, other: "Release") -> bool:
        return self._as_cmp() == other._as_cmp()

    def __gt__(self, other: "Release") -> bool:
        return self._as_cmp() > other._as_cmp()

    def __lt__(self, other: "Release") -> bool:
        return self._as_cmp() < other._as_cmp()


def matched_numerical_channel(
    risk: str, track_map: Mapping[str, List[str]]
) -> Optional[str]:
    """
    Given a risk, provide the most recently available channel matching that risk.

    @param risk: one of the 4 Risks
    @param track_map: mapping of kubernetes releases to available channels
    """
    if risk in RISKS:
        versions = ((Release.mk(k), v) for k, v in track_map.items())
        ordered = sorted(versions, reverse=True)
        for release, tracks in ordered:
            chan = f"{release}/{risk}"
            if chan in tracks:
                return chan


@dataclass
class ChannelRange:
    """Determine if channel is within a channel range.

    Usage:
        assert "latest/edge" in ChannelRange("1.18", "1.25/stable") # latest/<anything> is ignored
        assert "1.24/edge" in ChannelRange("1.18", "1.25/stable")   # within bounds inclusively
        assert "1.24/edge" in ChannelRange("1.18", None)            # No upper bound
        assert "1.24/edge" in ChannelRange(None, "1.25/stable")     # No lower bound
        assert "1.24/edge" in ChannelRange(None, None)              # No bounds
    """

    _min: Optional[str]
    _max: Optional[str]

    @property
    def min(self) -> Optional[Release]:
        """Release object representing the minimum."""
        return self._min and Release.mk(self._min)

    @property
    def max(self) -> Optional[Release]:
        """Release object representing the maximum."""
        return self._max and Release.mk(self._max)

    def __contains__(self, other: Union[str, Release]) -> bool:
        """Implements comparitor."""
        if isinstance(other, str) and other.startswith("latest"):
            return True
        if not isinstance(other, Release):
            other = Release.mk(str(other))
        if self.min and other < self.min:
            return False
        if self.max and other > self.max:
            return False
        return True


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


class CharmCmd(_WrappedCmd):
    def __init__(self, entity):
        super().__init__(entity, sh.charm.bake(_tee=True, _out=entity.echo))
        self.charm = self._run

    def build(self, *args, **kwargs):
        ret = self.charm.build(*args, **kwargs)
        assert not getattr(ret, "ok", None), "sh lib added an 'ok' attribute"
        ret.ok = True
        return ret


class CharmcraftCmd(_WrappedCmd):
    def __init__(self, entity):
        super().__init__(entity, sh.charmcraft.bake(_tee=True, _out=entity.echo))
        self.charmcraft = self._run

    def pack(self, *args, **kwargs):
        try:
            ret = self.charmcraft.pack(*args, **kwargs)
        except sh.ErrorReturnCode:
            self._echo(f"Failed to pack bundle in {kwargs.get('_cwd')}")
            raise
        (entity,) = re.findall(r"Created '(\S+)'", ret.stdout.decode(), re.MULTILINE)
        entity = Path(entity)
        self._echo(f"Packed Bundle :: {entity.name:^35}")
        return entity


class _CharmHub(CharmcraftCmd):
    STATUS_RESOURCE = re.compile(r"(\S+) \(r(\d+)\)")

    @staticmethod
    def _table_to_list(header, body):
        if not body:
            return []
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
    def info(name, **query):
        url = f"https://api.charmhub.io/v2/charms/info/{name}"
        resp = requests.get(url, params=query)
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

    def promote(self, charm_entity, from_channel, to_channels):
        self._echo(
            f"Promoting :: {charm_entity:^35} :: from:{from_channel} to: {to_channels}"
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
                    *(f"--channel={chan}" for chan in to_channels),
                    *resource_args,
                )
            )
        for args in calls:
            self.charmcraft.release(*args)

    def upload(self, dst_path):
        out = self.charmcraft.upload(dst_path)
        (revision,) = re.findall(
            r"Revision (\d+) of ", out.stdout.decode(), re.MULTILINE
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
            cls.base_dir = Path(os.environ.get("CHARM_BASE_DIR"))
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

        # poison base_dir to prevent `git rev-parse` from working in this subdirectory
        (self.base_dir / ".git").touch(0o664, exist_ok=True)

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
    def to_channels(self) -> List[str]:
        """
        Returns destination channels.

        Based on the build_args for historical reasons a *risk*
        can be returned in the list of channels which implies
        latest/<risk> when necessary.

        Numerical channels will always be in the format i.ii/risk
        """
        chan = self.db["build_args"].get("to_channel", None)
        numerical = matched_numerical_channel(chan, SNAP_K8S_TRACK_MAP)
        return list(filter(None, [chan, numerical]))

    def apply_channel_bounds(self, name: str, to_channels: List[str]) -> List[str]:
        """
        Applies boundaries to a charm or bundle's target channel.

        Uses the channel-range.min and channel-range.max arguments in self.artifacts
        to filter the channels list.
        """

        entity = next((_[name] for _ in self.artifacts if name in _.keys()), {})
        range_def = entity.get("channel-range", {})
        definitions = range_def.get("min"), range_def.get("max")
        assert all(isinstance(_, (str, type(None))) for _ in definitions)
        channel_range = ChannelRange(*definitions)
        return [channel for channel in to_channels if channel in channel_range]

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

    def promote_all(self, from_channel="unpublished", to_channels=("edge",)):
        """Promote set of charm artifacts in charmhub."""
        for charm_map in self.artifacts:
            for charm_name, charm_opts in charm_map.items():
                if not any(match in self.filter_by_tag for match in charm_opts["tags"]):
                    continue
                to_channels = self.apply_channel_bounds(charm_name, to_channels)
                _CharmHub(self).promote(charm_name, from_channel, to_channels)

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

    def __init__(self, build, name, opts):
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
        self.channel = self.build.db["build_args"]["to_channel"]
        self.reactive = False
        if self.build.build_type == BuildType.CHARM:
            self.type = "Charm"
            self.checkout_path = build.charms_dir / self.name
        elif self.build.build_type == BuildType.BUNDLE:
            self.type = "Bundle"
            self.checkout_path = build.repos_dir / opts.get("sub-repo", "")

        src_path = self.checkout_path / opts.get("subdir", "")

        self.downstream = opts.get("downstream")

        # prefer the jenkins build_args branch
        branch = self.build.db["build_args"].get("branch")

        if not branch:
            # if there is no branch build arg, use the branch value from the charm stanza
            branch = opts.get("branch")

        if not branch and self.downstream:
            # if branch not specified, use repo's default branch
            auth = os.environ.get("CDKBOT_GH_USR"), os.environ.get("CDKBOT_GH_PSW")
            branch = default_gh_branch(self.downstream, ignore_errors=True, auth=auth)

        self.branch = branch or "main"

        self.layer_path = src_path / "layer.yaml"
        self.src_path = str(src_path.absolute())
        self.dst_path = str(Path(self.src_path) / f"{self.name}.charm")

        # Bundle or charm opts as defined in the layer include
        self.opts = opts
        self.namespace = opts.get("namespace")

        # Entity path, ie. kubernetes-worker
        self.entity = name

        # Entity path with current revision (from target channel)
        self.full_entity = self._get_full_entity()

        # Entity path with new revision (from pushing)
        self.new_entity = None

    def __str__(self):
        """Represent build entity as a string."""
        return f"<BuildEntity: {self.name} ({self.full_entity}) (reactive charm: {self.reactive})>"

    def echo(self, msg):
        """Click echo wrapper."""
        click.echo(f"[{self.name}] {msg}")

    def _get_full_entity(self):
        """Grab identifying revision for charm's channel."""
        return f"{self.entity}:{self.channel}"

    def download(self, fname):
        """Fetch single file from associated store/charm/channel."""
        if not self.full_entity:
            return None
        name, channel = self.full_entity.rsplit(":")
        info = _CharmHub.info(
            name, channel=channel, fields="default-release.revision.download.url"
        )
        try:
            url = info["default-release"]["revision"]["download"]["url"]
        except (KeyError, TypeError):
            self.echo(f"Failed to find in charmhub.io \n{info}")
            return None
        self.echo(f"Downloading {fname} from {url}")
        resp = requests.get(url, stream=True)
        if resp.ok:
            yaml_file = zipfile.Path(BytesIO(resp.content)) / fname
            return yaml.safe_load(yaml_file.read_text())
        self.echo(f"Failed to read {fname} due to {resp.status_code} - {resp.content}")

    def version_identification(self, source):
        comparisons = ["rev", "url"]
        version_id = []
        if not self.reactive and source == "local":
            version_id = [{"rev": self.commit(short=True), "url": self.entity}]
        elif not self.reactive and source == "remote":
            info = _CharmHub.info(
                self.name,
                channel=self.channel,
                fields="default-release.revision.version",
            )
            version = info.get("default-release", {}).get("revision", {}).get("version")
            version_id = [{"rev": version, "url": self.entity}] if version else None
        elif self.reactive and source == "local":
            version_id = [
                {k: curr[k] for k in comparisons}
                for curr in self.build.db["pull_layer_manifest"]
            ]

            # Check the current git cloned charm repo commit and add that to
            # current pull-layer-manifest as that would not be known at the
            # time of pull_layers
            version_id.append({"rev": self.commit(), "url": self.name})
        elif self.reactive and source == "remote":
            build_manifest = self.download(".build.manifest")
            if not build_manifest:
                self.echo("No build.manifest located.")
                version_id = None
            else:
                version_id = [
                    {k: i[k] for k in comparisons} for i in build_manifest["layers"]
                ]
        else:
            self.echo(f"Unexpected source={source} for determining version")
        return version_id

    @property
    def has_changed(self):
        """Determine if the charm/layers commits have changed since last publish."""
        local = self.version_identification("local")
        remote = self.version_identification("remote")

        if remote is None:
            self.echo("No released versions in charmhub. Building...")
            return True

        the_diff = [rev for rev in remote if rev not in local]
        if the_diff:
            self.echo(f"Changes found {the_diff}")
            return True

        self.echo(f"No changes found in {self.entity}")
        return False

    def commit(self, short=False):
        """Commit hash of downstream repo."""
        if not Path(self.src_path).exists():
            raise BuildException(f"Could not locate {self.src_path}")
        if short:
            git_commit = git("describe", dirty=True, always=True, _cwd=self.src_path)
        else:
            git_commit = git("rev-parse", "HEAD", _cwd=self.src_path)
        return git_commit.stdout.decode().strip()

    def _read_metadata_resources(self):
        if self.dst_path.endswith(".charm"):
            metadata_path = zipfile.Path(self.dst_path) / "metadata.yaml"
        else:
            metadata_path = Path(self.dst_path) / "metadata.yaml"
        metadata = yaml.safe_load(metadata_path.read_text())
        return metadata.get("resources", {})

    def setup(self):
        """Set up directory for charm build."""
        repository = f"https://github.com/{self.downstream}"
        self.echo(f"Cloning repo from {repository} branch {self.branch}")

        os.makedirs(self.checkout_path)
        ret = cmd_ok(
            f"git clone --branch {self.branch} {repository} {self.checkout_path}",
            echo=self.echo,
        )
        if not ret.ok:
            raise BuildException("Clone failed")

        self.reactive = self.layer_path.exists()

    def charm_build(self):
        """Perform a build against charm/bundle."""
        lxc = os.environ.get("charmcraft_lxc")
        ret = SimpleNamespace(ok=False)
        if "override-build" in self.opts:
            self.echo("Override build found, running in place of charm build.")
            ret = script(
                self.opts["override-build"],
                cwd=self.src_path,
                charm=self.name,
                echo=self.echo,
            )
        elif self.reactive:
            args = "-r --force -i https://localhost --charm-file"
            self.echo(f"Building with: charm build {args}")
            ret = CharmCmd(self).build(*args.split(), _cwd=self.src_path)
        elif lxc:
            self.echo(f"Building in container {lxc}")
            repository = f"https://github.com/{self.downstream}"
            charmcraft_script = (
                "#!/bin/bash -eux\n"
                f"source {Path(__file__).parent / 'charmcraft-lib.sh'}\n"
                f"ci_charmcraft_pack {lxc} {repository} {self.branch} {self.opts.get('subdir', '')}\n"
                f"ci_charmcraft_copy {lxc} {self.dst_path}\n"
            )
            ret = script(charmcraft_script, echo=self.echo)
        else:
            self.echo("No 'charmcraft_lxc' container available")

        if not ret.ok:
            self.echo("Failed to build, aborting")
            raise BuildException(f"Failed to build {self.name}")

    def push(self):
        """Pushes a built charm to Charmhub."""
        if "override-push" in self.opts:
            self.echo("Override push found, running in place of charm push.")
            args = dict(
                cwd=self.src_path,
                charm=self.name,
                echo=self.echo,
            )
            if self.namespace:
                args["namespace"] = self.namespace
            script(self.opts["override-push"], **args)
            return

        self.echo(
            f"Pushing {self.type}({self.name}) from {self.dst_path} to {self.entity}"
        )
        self.new_entity = _CharmHub(self).upload(self.dst_path)

    def attach_resources(self):
        """Assemble charm's resources and associate in charmhub."""
        out_path = Path(self.src_path) / "tmp"
        os.makedirs(str(out_path), exist_ok=True)
        resource_spec = yaml.safe_load(Path(self.build.resource_spec).read_text())
        resource_spec = resource_spec.get(self.name, {})
        context = dict(
            src_path=self.src_path,
            out_path=out_path,
        )

        # Build any custom resources.
        resource_builder = self.opts.get("build-resources", None)
        if resource_builder and not resource_spec:
            raise BuildException(
                f"Custom build-resources specified for {self.name} but no spec found"
            )
        if resource_builder:
            resource_builder = resource_builder.format(**context)
            self.echo("Running custom build-resources")
            ret = script(resource_builder, echo=self.echo)
            if not ret.ok:
                raise BuildException("Failed to build custom resources")

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
                    resource_fmt.format(**context),
                )

        self.echo(f"Attaching resources:\n{pformat(resource_spec)}")
        # Attach all resources.
        for resource_name, resource in resource_spec.items():
            _CharmHub(self).upload_resource(self.entity, resource_name, resource)

    def promote(self, from_channel="unpublished", to_channels=("edge",)):
        """Promote charm and its resources from a channel to another."""
        track = self.build.db["build_args"].get("track") or "latest"
        ch_channels = [
            f"{track}/{chan.lower()}"
            if (chan.lower() in RISKS and from_channel == "unpublished")
            else chan
            for chan in to_channels
        ]
        ch_channels = self.build.apply_channel_bounds(self.entity, ch_channels)
        _CharmHub(self).promote(self.entity, from_channel, ch_channels)


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
        remote_bundle = self.download("bundle.yaml")

        local_built_bundle = yaml.safe_load(
            (Path(self.dst_path) / "bundle.yaml").read_text(encoding="utf8")
        )

        if remote_bundle != local_built_bundle:
            self.echo("Local bundle differs.")
            return True

        self.echo(f"No differences found, not pushing new bundle {self.entity}")
        return False

    def bundle_build(self, to_channel):
        if not self.opts.get("skip-build"):
            cmd = f"{self.src_path}/bundle -n {self.name} -o {self.dst_path} -c {to_channel} {self.opts['fragments']}"
            self.echo(f"Running {cmd}")
            cmd_ok(cmd, echo=self.echo)
        else:
            # If we're not building the bundle from the repo, we have
            # to copy it to the expected output location instead.
            shutil.copytree(
                Path(self.src_path) / self.opts.get("subdir", ""), self.dst_path
            )

        # If we're building for charmhub, it needs to be packed
        dst_path = Path(self.dst_path)
        charmcraft_yaml = dst_path / "charmcraft.yaml"
        if not charmcraft_yaml.exists():
            contents = {
                "type": "bundle",
                "parts": {
                    "bundle": {
                        "prime": [
                            str(_.relative_to(dst_path))
                            for _ in dst_path.glob("**/*")
                            if _.is_file()
                        ]
                    }
                },
            }
            with charmcraft_yaml.open("w") as fp:
                yaml.safe_dump(contents, fp)
        self.dst_path = str(CharmcraftCmd(self).pack(_cwd=dst_path))

    def reset_dst_path(self):
        """Reset the dst_path in order to facilitate multiple bundle builds by the same entity."""

        def delete_file_or_dir(d):
            cur_dst_path = Path(d)
            try:
                cur_dst_path.unlink(missing_ok=True)
            except IsADirectoryError:
                shutil.rmtree(cur_dst_path)

        delete_file_or_dir(self.dst_path)  # delete any zip'd bundle file
        self.dst_path = str(self.opts["dst_path"])  # reset the state
        delete_file_or_dir(self.dst_path)  # delete any unzipped bundle directory


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
    default="",
)
@click.option(
    "--layer-branch",
    required=True,
    help="Git branch to pull layers/interfaces from",
    default="main",
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

            charm_entity = BuildEntity(build_env, charm_name, charm_opts)
            entities.append(charm_entity)
            click.echo(f"Queued {charm_entity.entity} for building")

    failed_entities = []

    for entity in entities:
        entity.echo("Starting")
        try:
            entity.setup()
            entity.echo(f"Details: {entity}")

            if not build_env.force:
                if not entity.has_changed:
                    continue
            else:
                entity.echo("Build forced.")

            entity.charm_build()

            entity.push()
            entity.attach_resources()
            entity.promote(to_channels=build_env.to_channels)
        except Exception:
            entity.echo(traceback.format_exc())
            failed_entities.append(entity)
        finally:
            entity.echo("Stopping")

    if any(failed_entities):
        count = len(failed_entities)
        plural = "s" if count > 1 else ""
        raise SystemExit(
            f"Encountered {count} Charm Build Failure{plural}:\n\t"
            + ", ".join(ch.name for ch in failed_entities)
        )

    build_env.save()


@cli.command()
@click.option("--bundle-list", required=True, help="list of bundles in YAML format")
@click.option(
    "--bundle-branch",
    default="main",
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
    default="https://github.com/charmed-kubernetes/bundle.git",
)
@click.option(
    "--track", required=True, help="track to promote charm to", default="latest"
)
@click.option(
    "--to-channel", required=True, help="channels to promote bundle to", default="edge"
)
def build_bundles(
    bundle_list, bundle_branch, filter_by_tag, bundle_repo, track, to_channel
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

            build_entity = BundleBuildEntity(build_env, bundle_name, bundle_opts)
            entities.append(build_entity)

    for entity in entities:
        entity.echo("Starting")
        try:
            if "downstream" in entity.opts:
                # clone bundle repo override
                entity.setup()
            entity.echo(f"Details: {entity}")
            for channel in build_env.to_channels:
                entity.bundle_build(channel)
                entity.push()
                entity.promote(to_channels=[channel])
                entity.reset_dst_path()
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
def promote(charm_list, filter_by_tag, from_channel, to_channel):
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
        from_channel=from_channel, to_channels=build_env.to_channels
    )


if __name__ == "__main__":
    cli()
