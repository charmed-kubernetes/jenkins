# -*- coding: utf-8 -*-
"""
charms.py - Interface to building and publishing charms.

Make sure that charm environments variables are set appropriately

CHARM_BUILD_DIR, CHARM_LAYERS_DIR, CHARM_INTERFACES_DIR

See `charm build --help` for more information.

Usage:

  tox -e py -- python3 jobs/build-charms/main.py build \
     --charm-list jobs/includes/charm-support-matrix.inc \
     --resource-spec jobs/build-charms/resource-spec.yaml

  tox -e py -- python3 jobs/build-charms/main.py --help
"""

import os
import inspect
import traceback
from io import BytesIO
import zipfile
from pathlib import Path
from collections import defaultdict
from cilib.ch import ensure_charm_track
from cilib.github_api import Repository
from enum import Enum, unique
from sh.contrib import git
from cilib.git import default_gh_branch
from cilib.enums import SNAP_K8S_TRACK_MAP, K8S_SERIES_MAP, K8S_CHARM_SUPPORT_ARCHES
from cilib.service.aws import Store
from cilib.run import script
from cilib.version import ChannelRange, Release, RISKS
from dataclasses import dataclass, field
from functools import partial
from datetime import datetime
from types import SimpleNamespace
from typing import Any, Iterable, List, Mapping, Optional, Set, Tuple

from multiprocessing.pool import ThreadPool
from pprint import pformat
import click
import shutil
import sh
import yaml
import json
import requests
import re


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


def generate_manifest(reactive_charm, archs):
    """Generate a manifest.yaml for a reactive charm.

    Charmhub requires a manifest.yaml in order to identify
    ubuntu series starting with jammy.
    """
    metadata_path = Path(reactive_charm) / "metadata.yaml"
    manifest_path = Path(reactive_charm) / "manifest.yaml"
    if not metadata_path.exists() or manifest_path.exists():
        return

    class NoAliasDumper(yaml.SafeDumper):
        """Prevent yaml aliases in manifest.yaml"""

        def ignore_aliases(self, _data):
            return True

    def _generate_base(series: str):
        return {
            "architectures": archs,
            "channel": K8S_SERIES_MAP[series.lower()],
            "name": "ubuntu",
        }

    def _generate_tools():
        ret = json.loads(sh.charm.version(format="json"))
        return {
            "charmtool-version": ret["charm-tools"]["version"],
            "charmtool-started-at": datetime.utcnow().isoformat() + "Z",
        }

    manifest = {
        "analysis": {
            "attributes": [
                {"name": "language", "result": "python"},
                {"name": "framework", "result": "reactive"},
            ],
        }
    }

    metadata = yaml.safe_load(metadata_path.read_bytes())
    manifest["bases"] = [_generate_base(series) for series in metadata["series"]]
    manifest.update(**_generate_tools())
    with manifest_path.open("w") as fwrite:
        yaml.dump(manifest, fwrite, Dumper=NoAliasDumper)
    return manifest_path


class BuildException(Exception):
    """Define build Exception."""


@unique
class BuildType(Enum):
    """Enumeration for the build type."""

    CHARM = 1
    BUNDLE = 2


@unique
class LayerType(Enum):
    """Enumeration for the layer type."""

    LAYER = 1
    INTERFACE = 2


def _next_match(seq, predicate=lambda _: _, default=None):
    """Finds the first item of an iterable matching a predicate, or default if none exists."""
    return next(filter(predicate, seq), default)


class _WrappedCmd:
    def __init__(self, entity, command: str):
        """Create an object which tees output from the command also to the log."""
        self._echo = entity.echo
        self._command = getattr(sh, command).bake(
            _tee=True,
            _out=partial(entity.echo, nl=False),
            _truncate_exc=False,
        )
        setattr(self, command, self._command)

    def __getattr__(self, name):
        """Maps sub through to the baked sh command."""
        return getattr(self._command, name)


class Docker(_WrappedCmd):
    """Creates a sh command for docker where the output is tee'd."""

    def __init__(self, entity):
        super().__init__(entity, "docker")


class Charm(_WrappedCmd):
    """Creates a sh command for charm where the output is tee'd."""

    def __init__(self, entity):
        super().__init__(entity, "charm")

    def pull_source(self, *args, **kwargs):
        return self.charm("pull-source", *args, **kwargs)


class Charmcraft(_WrappedCmd):
    """Creates a sh command for charmcraft where the output is tee'd."""

    def __init__(self, entity):
        super().__init__(entity, "charmcraft")

    def pack(self, *args, **kwargs):
        try:
            ret = self.charmcraft.pack(*args, **kwargs)
        except sh.ErrorReturnCode:
            self._echo(f"Failed to pack bundle in {kwargs.get('_cwd')}")
            raise
        (entity,) = re.findall(r"Created '(\S+)'", ret, re.MULTILINE)
        entity = Path(entity)
        self._echo(f"Packed Bundle :: {entity.name:^35}")
        return entity


@dataclass
class Base:
    name: str
    channel: str
    architecture: str

    def __str__(self) -> str:
        return f"{self.name} {self.channel} ({self.architecture})"


@dataclass
class ResourceRevision:
    name: str
    revision: int


@dataclass
class ReleaseStatus:
    status: str
    channel: str
    version: Optional[int]
    revision: Optional[str]
    resources: Optional[List[ResourceRevision]]

    @classmethod
    def from_dict(cls, **kwds) -> "ResourceRevision":
        resources = kwds.pop("resources") or []
        kwds["resources"] = [ResourceRevision(**_) for _ in resources]
        return cls(
            **{k: v for k, v in kwds.items() if k in inspect.signature(cls).parameters}
        )


@dataclass
class MappingStatus:
    base: Optional[Base]
    releases: List[ReleaseStatus]

    @classmethod
    def from_dict(cls, base, releases) -> "MappingStatus":
        base = Base(**base) if base else None
        releases = [ReleaseStatus.from_dict(**_) for _ in releases or []]
        return cls(base, releases)


@dataclass
class TrackStatus:
    track: str
    mappings: List[MappingStatus]

    @classmethod
    def from_dict(cls, track, mappings) -> "TrackStatus":
        mappings = [MappingStatus.from_dict(**_) for _ in mappings]
        return cls(track, mappings)


class _CharmHub(Charmcraft):
    STATUS_RESOURCE = re.compile(r"(\S+) \(r(\d+)\)")
    BASE_RE = re.compile(r"(\S+) (\S+) \((\S+)\)")

    @staticmethod
    def _table_to_list(header, body) -> List[Mapping[str, str]]:
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

    def status(self, charm_entity) -> List[TrackStatus]:
        """Read CLI Table output from charmcraft status and parse."""
        charm_status_str = self.charmcraft.status(
            charm_entity, format="json", _out=None
        )
        return [TrackStatus.from_dict(**_) for _ in json.loads(charm_status_str)]

    def revisions(self, charm_entity):
        """Read CLI Table output from charmcraft revisions and parse."""
        charm_status = self.charmcraft.revisions(charm_entity)
        header, *body = charm_status.splitlines()
        return self._table_to_list(header, body)

    def resources(self, charm_entity):
        """Read CLI Table output from charmcraft resources and parse."""
        charmcraft_out = self.charmcraft.resources(charm_entity)
        header, *body = charmcraft_out.splitlines()
        return self._table_to_list(header, body)

    def resource_revisions(self, charm_entity, resource):
        """Read CLI Table output from charmcraft resource-revisions and parse."""
        charmcraft_out = self.charmcraft("resource-revisions", charm_entity, resource)
        header, *body = charmcraft_out.splitlines()
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

    def release(self, entity: str, artifact: "Artifact", to_channels: List[str]):
        self._echo(f"Releasing :: {entity:^35} :: to: {to_channels}")
        rev_args = f"--revision={artifact.rev}"
        for channel in to_channels:
            ensure_charm_track(entity, channel)
        channel_args = [f"--channel={chan}" for chan in to_channels]
        resource_rev_args = [
            f"--resource={rsc.name}:{rsc.rev}" for rsc in artifact.resources
        ]
        args = [entity, rev_args] + channel_args + resource_rev_args
        self.charmcraft.release(*args)

    def promote(self, charm_entity, from_channel, to_channels, dry_run):
        self._echo(
            f"Promoting :: {charm_entity:^35} :: from:{from_channel} to: {to_channels}"
        )
        charm_status = [
            # Get all the releases and associated bases
            (release, mapping.base)
            # where the track matches the from_channel
            for track in self.status(charm_entity)
            if from_channel.startswith(track.track)
            # when that track has a base mapping
            for mapping in track.mappings
            if mapping.base
            # if the from_channel exact matches, and it's not a tracking release
            # The charm was really released to this channel
            for release in mapping.releases
            if release.channel == from_channel and release.status != "tracking"
        ]

        calls = defaultdict(list)
        for release, base in charm_status:
            if release.revision is None:
                continue
            resource_args = (
                f"--resource={rsc.name}:{rsc.revision}" for rsc in release.resources
            )
            args = (
                charm_entity,
                f"--revision={release.revision}",
                *resource_args,
                *(f"--channel={chan}" for chan in to_channels),
            )
            calls[args].append(base)

        # So, its very likely there could be multiple charms in this
        # from_channel which need to be promoted to the to_channels.

        # due to different charm revisions for a different base
        # for example coredns could have a different charm revision
        # for arm64 and amd64 -- each should be promoted

        for args, bases in calls.items():
            base_str = "# " + ", ".join(map(str, bases))
            debug_cmd = " ".join(map(str, ["charmcraft", "release", *args]))
            self._echo(f"\n{base_str}\n{debug_cmd}")
            if not dry_run:
                self.charmcraft.release(*args)

    def upload(self, dst_path) -> int:
        out = self.charmcraft.upload(dst_path)
        self._echo(f"Upload   :: returns {out}")
        (revision,) = re.findall(r"Revision (\d+) ", out, re.MULTILINE)
        return int(revision)

    def upload_resource(self, charm_entity, resource: "CharmResource") -> int:
        kwargs = resource.upload_args
        out = self.charmcraft("upload-resource", charm_entity, resource.name, **kwargs)
        self._echo(f"Upload Resource   :: returns {out}")
        (revision,) = re.findall(r"Revision (\d+) ", out, re.MULTILINE)
        return int(revision)


def apply_channel_bounds(opts: Mapping[str, Any], to_channels: List[str]) -> List[str]:
    """
    Applies boundaries to a charm or bundle's target channel.

    Uses the channel-range.min and channel-range.max arguments in self.job_list
    to filter the channels list.
    """

    channel_range = ChannelRange.from_dict(opts)
    return [channel for channel in to_channels if channel in channel_range]


class BuildEnv:
    """Charm or Bundle build data class."""

    REV = re.compile("rev: ([a-zA-Z0-9]+)")

    def __new__(cls, *args, **kwargs):
        """Initialize class variables used during the build from the CI environment."""
        try:
            cls.build_tag = os.environ.get("BUILD_TAG")
            cls.base_dir = Path(os.environ.get("CHARM_BASE_DIR"))
            cls.build_dir = Path(os.environ.get("CHARM_BUILD_DIR"))
            cls.layers_dir = Path(os.environ.get("CHARM_LAYERS_DIR"))
            cls.interfaces_dir = Path(os.environ.get("CHARM_INTERFACES_DIR"))
            cls.charms_dir = Path(os.environ.get("CHARM_CHARMS_DIR"))
            cls.work_dir = Path(os.environ.get("WORKSPACE"))
            cls.tmp_dir = cls.work_dir / "tmp"
            cls.home_dir = Path(os.environ.get("HOME"))
        except TypeError as ex:
            raise BuildException(
                "CHARM_BUILD_DIR, CHARM_LAYERS_DIR, CHARM_INTERFACES_DIR, WORKSPACE, HOME: "
                "Unable to find some or all of these charm build environment variables."
            ) from ex
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
    def job_list(self):
        """List of charms or bundles to process."""
        return yaml.safe_load(
            Path(self.db["build_args"]["job_list"]).read_text(encoding="utf8")
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
    def filter_by_tag(self) -> Set[str]:
        """Filter tags defined by the build job."""
        return set(self.db["build_args"].get("filter_by_tag", []))

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
        chans: List[str] = self.db["build_args"].get("to_channel", None).split(",")
        numerical = [
            matched_numerical_channel(chan, SNAP_K8S_TRACK_MAP) for chan in chans
        ]
        return list(filter(None, {*chans, *numerical}))

    @property
    def from_channel(self):
        """Get source channel."""
        return self.db["build_args"].get("from_channel", None)

    @property
    def force(self):
        """Get if we should force a build."""
        return self.db["build_args"].get("force", None)

    def echo(self, msg, **kwds):
        """Click echo wrapper."""
        click.echo(f"[BuildEnv] {msg}", **kwds)

    def save(self):
        """Store build metadata into stateful db."""
        self.echo("Saving build")
        self.echo(dict(self.db))
        self.db_json.write_text(json.dumps(dict(self.db)))
        self.store.put_item(Item=dict(self.db))

    @property
    def track(self):
        return self.db["build_args"].get("track") or "latest"

    def promote_all(self, from_channel="beta", to_channels=("edge",), dry_run=True):
        """Promote set of charms in charmhub."""
        if from_channel.lower() in RISKS:
            from_channel = f"{self.track}/{from_channel.lower()}"
        assert (
            from_channel != "unpublished"
        ), "It's unwise to promote unpublished charms."
        to_channels = [
            f"{self.track}/{chan.lower()}" if (chan.lower() in RISKS) else chan
            for chan in to_channels
        ]
        failed_entities = []
        for charm_map in self.job_list:
            for charm_name, charm_opts in charm_map.items():
                if not any(tag in self.filter_by_tag for tag in charm_opts["tags"]):
                    continue
                ch_channels = apply_channel_bounds(charm_opts, to_channels)
                try:
                    _CharmHub(self).promote(
                        charm_name, from_channel, ch_channels, dry_run
                    )
                except Exception:
                    self.echo(traceback.format_exc())
                    failed_entities.append(charm_name)

        if any(failed_entities):
            count = len(failed_entities)
            plural = "s" if count > 1 else ""
            raise SystemExit(
                f"Encountered {count} Promote All Failure{plural}:\n\t"
                + ", ".join(failed_entities)
            )

    def download(self, layer_name):
        """Pull layer source from the charm store."""
        out = Charm(self).pull_source(
            "-i", self.layer_index, "-b", self.layer_branch, layer_name
        )
        layer_manifest = {
            "rev": self.REV.search(out).group(1),
            "url": layer_name,
        }
        return layer_manifest

    def pull_layers(self):
        """Clone all downstream layers to be processed locally when doing charm builds."""
        layers_to_pull = [
            layer_name
            for layer in self.layers
            for layer_name, layer_ops in layer.items()
            if layer_ops.get("build_cache") is not False
        ]
        pool = ThreadPool()
        results = pool.map(self.download, layers_to_pull)

        self.db["pull_layer_manifest"] = list(results)


@unique
class Arch(Enum):
    ALL = "all"
    UNKNOWN = "unknown"
    AMD64 = "amd64"
    ARM64 = "arm64"
    ARMHF = "armhf"
    PPC64EL = "ppc64el"
    S390X = "s390x"

    @classmethod
    def from_value(cls, value: str) -> "Arch":
        for arch in cls:
            if arch.value == value:
                return arch
        if value == "arm":
            return arch.ARMHF
        return Arch.UNKNOWN


@unique
class Series(Enum):
    ALL = "all"
    UNKNOWN = "unknown"
    XENIAL = "16.04"
    BIONIC = "18.04"
    FOCAL = "20.04"
    JAMMY = "22.04"

    @classmethod
    def from_value(cls, value: str) -> "Series":
        for series in cls:
            if series.value == value:
                return series
        return Series.UNKNOWN


@unique
class ResourceKind(Enum):
    FILEPATH = "filepath"
    IMAGE = "image"


@dataclass
class CharmResource:
    name: str
    kind: Optional[ResourceKind] = None
    value: Optional[str] = None  # location (filepath or image-id)
    rev: Optional[int] = None  # set when uploaded or when lookedup

    @property
    def upload_args(self) -> Mapping[str, str]:
        return {self.kind.value: str(self.value)}


@dataclass
class Artifact:
    charm_or_bundle: Path
    arch: Arch = Arch.ALL
    series: Series = Series.ALL
    rev: int = None  # set when uploaded
    resources: List[CharmResource] = field(default_factory=list)

    def __str__(self) -> str:
        return f"File: {self.charm_or_bundle.name} for arch={self.arch} and series={self.series}"

    @staticmethod
    def _from_run_on_base(run_on_base: str) -> Iterable[Tuple[Arch, Series]]:
        if not run_on_base.startswith("ubuntu-"):
            return
        base, *archs = run_on_base.split("-")[1:]
        for arch in archs:
            yield Arch.from_value(arch), Series.from_value(base)

    @classmethod
    def from_charm(cls, charm_file: Path) -> ["Artifact"]:
        """
        Parsed according to charmcraft file output.
        https://discourse.charmhub.io/t/charmcraft-bases-provider-support/4713
        """
        run_on_bases = charm_file.stem.split("_")[1:]
        base_arches = list(
            pair for each in run_on_bases for pair in Artifact._from_run_on_base(each)
        )
        arch, series = base_arches[0]
        if len(base_arches) == 1:
            # single series, single arch     --> Series._specific_, Arch._specific_
            return cls(charm_file, arch, series)
        if len(set(arch for arch, _ in base_arches)) == 1:
            # multiple series, single arch   --> Series.ALL       , Arch._specific_
            return cls(charm_file, arch, Series.ALL)
        if len(set(series for _, series in base_arches)) == 1:
            # single series, multiple arch   --> Series._specific_, Arch.ALL
            return cls(charm_file, Arch.ALL, series)
        return cls(charm_file, Arch.ALL, Series.ALL)

    @property
    def arch_docker(self) -> str:
        """manage docker platforms with slightly different identifiers."""
        if self.arch == Arch.PPC64EL:
            return "ppc64le"
        elif self.arch in (Arch.ALL, Arch.UNKNOWN):
            return Arch.AMD64.value
        else:
            return self.arch.value


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
            branch = default_gh_branch(self.downstream, ignore_errors=True)

        self.branch = branch or "main"

        self.layer_path = src_path / "layer.yaml"
        self.src_path = str(src_path.absolute())
        self.artifacts: List[Artifact] = []

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

    def echo(self, msg, **kwds):
        """Click echo wrapper."""
        click.echo(f"[{self.name}] {msg}", **kwds)

    def _get_full_entity(self):
        """Grab identifying revision for charm's channel."""
        return f"{self.entity}:{self.channel}"

    def download(self, fname):
        """Fetch single file from associated store/charm/channel."""
        name, channel = self.entity, self.channel
        info = _CharmHub.info(
            name, channel=channel, fields="default-release.revision.download.url"
        )
        self.echo(f"Received channel info\n{yaml.safe_dump(info)}")
        try:
            url = info["default-release"]["revision"]["download"]["url"]
        except (KeyError, TypeError):
            self.echo(f"Failed to find in charmhub.io \n{info}")
            return None
        self.echo(f"Downloading {fname or ''} from {url}")
        resp = requests.get(url, stream=True)
        if resp.ok:
            zip_entity = zipfile.ZipFile(BytesIO(resp.content))
            if fname:
                yaml_file = zipfile.Path(zip_entity) / fname
                return yaml.safe_load(yaml_file.read_text())
            elif fname is None:
                return zip_entity
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
            self.echo(f"Received channel info \n{yaml.safe_dump(info)}")
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
    def charm_changes(self):
        """Determine if any charm|layers commits have changed since last publish."""
        locals = self.version_identification("local")
        remotes = self.version_identification("remote")

        if remotes is None:
            self.echo("No released versions in charmhub. Building...")
            return True

        locals = {loc["url"]: loc["rev"] for loc in locals}
        remotes = {rem["url"]: rem["rev"] for rem in remotes}
        the_diff = {k: remotes[k] for k in remotes if locals[k] != remotes[k]}

        if the_diff:
            all_differences = {
                k: f"local: {locals.get(k)} remote: {remotes[k]}" for k in the_diff
            }
            self.echo(f"Changes found\n{yaml.safe_dump(all_differences)}")
            return True

        self.echo(f"No changes found in {self.entity}")
        return False

    def commit(self, short=False):
        """Commit hash of downstream repo."""
        if not Path(self.src_path).exists():
            raise BuildException(f"Could not locate {self.src_path}")
        if short:
            git_commit = git("rev-parse", "--short", "HEAD", _cwd=self.src_path)
        else:
            git_commit = git("rev-parse", "HEAD", _cwd=self.src_path)
        return git_commit.strip()

    def _read_metadata_resources(self, artifact: Artifact):
        search_path = artifact.charm_or_bundle
        if search_path.suffix == ".charm":
            metadata_path = zipfile.Path(search_path) / "metadata.yaml"
        else:
            metadata_path = Path(search_path) / "metadata.yaml"
        metadata = yaml.safe_load(metadata_path.read_text())
        return metadata.get("resources", {})

    def setup(self):
        """Set up directory for charm build."""
        repository = f"https://github.com/{self.downstream}"
        self.echo(f"Cloning repo from {repository} branch {self.branch}")

        os.makedirs(self.checkout_path)
        try:
            git(
                "clone",
                repository,
                self.checkout_path,
                branch=self.branch,
                _tee=True,
                _out=self.echo,
            )
        except sh.ErrorReturnCode as ex:
            raise BuildException("Clone failed") from ex

        self.reactive = self.layer_path.exists()

    def within_channel_bounds(self, to_channels):
        """Check if there's a valid channel to publish to."""
        return apply_channel_bounds(self.opts, to_channels)

    def charm_build(self):
        """Perform a build against charm/bundle."""
        lxc = os.environ.get("charmcraft_lxc")
        ret = SimpleNamespace(ok=False)
        charm_path = Path(self.src_path, f"{self.name}.charm")
        if "override-build" in self.opts:
            self.echo("Override build found, running in place of charm build.")
            ret = script(
                self.opts["override-build"],
                cwd=self.src_path,
                charm=self.name,
                echo=self.echo,
            )
        elif self.reactive:
            supported_architectures = (
                self.opts.get("architectures") or K8S_CHARM_SUPPORT_ARCHES
            )
            manifest_path = generate_manifest(self.src_path, supported_architectures)
            if manifest_path:
                self.echo(f"Manifest path generated: {manifest_path}")
            else:
                self.echo("Manifest path not generated.")
            args = "-r --force -i https://localhost --charm-file"
            self.echo(f"Building with: charm build {args}")
            try:
                Charm(self).build(*args.split(), _cwd=self.src_path)
                ret.ok = True
            except sh.ErrorReturnCode as e:
                self.echo(e.stderr)
        elif lxc:
            msg = f"Consider moving {self.name} to launchpad builder"
            border = "-".join("=" * (len(msg) // 2 + 1))
            self.echo("\n".join((border, msg, border)))
            self.echo(f"Building in container {lxc}.")
            repository = f"https://github.com/{self.downstream}"
            charmcraft_script = (
                "#!/bin/bash -eux\n"
                f"source {Path(__file__).parent / 'charmcraft-lib.sh'}\n"
                f"ci_charmcraft_pack {lxc} {repository} {self.branch} {self.opts.get('subdir', '')}\n"
                f"ci_charmcraft_copy {lxc} {charm_path}\n"
            )
            ret = script(charmcraft_script, echo=self.echo)
        else:
            self.echo("No 'charmcraft_lxc' container available")

        if not ret.ok:
            self.echo("Failed to build, aborting")
            raise BuildException(f"Failed to build {self.name}")
        self.artifacts.append(Artifact(charm_path, Arch.ALL))

    @property
    def repository(self) -> Optional[Repository]:
        """Create object to interact with the base repository."""
        if self.downstream:
            return Repository.with_session(*self.downstream.split("/"))

    def push(self, artifact: Artifact):
        """Pushes a built charm to Charmhub."""
        if "override-push" in self.opts:
            self.echo("Override push found, running in place of charmcraft upload.")
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
            f"Uploading {self.type}({self.name}) from {artifact} to {self.entity}"
        )
        artifact.rev = _CharmHub(self).upload(artifact.charm_or_bundle)
        self.tag(f"{self.name}-{artifact.rev}")

    def tag(self, tag: str) -> bool:
        """Tag current commit in this repo with a lightweigh tag."""
        tagged = False
        current_sha = self.commit()
        if repo := self.repository:
            ref = repo.get_ref(tag=tag, raise_on_error=False)
            ref_not_found = ref.get("message", "").lower() == "not found"
            ref_obj_sha = ref.get("object", {}).get("sha", "")
            assert ref_not_found or ref_obj_sha, f"Unexpected ref-object: ref={ref}"
            if ref_not_found:
                self.echo(f"Tagging {self.type}({self.name}) with {tag}")
                tagged = repo.create_ref(current_sha, tag=tag)
            elif ref_obj_sha.lower() == current_sha.lower():
                self.echo(f"Correct Tag {self.type}({self.name}) with {tag} exists")
                tagged = True
            else:
                raise BuildException(
                    f"Tag {tag} of {self.type}({self.name}) exists on a different commit\n"
                    f"   current: '{current_sha}' != tag: '{ref_obj_sha}'"
                )
        return tagged

    @property
    def _resource_path(self) -> Path:
        out_path = Path(self.src_path, "tmp")
        out_path.mkdir(parents=True, exist_ok=True)
        return out_path

    @property
    def _resource_spec(self):
        resource_spec = yaml.safe_load(Path(self.build.resource_spec).read_text())
        return resource_spec.get(self.name, {})

    def resource_build(self):
        """Build all charm custom resources."""
        context = dict(
            src_path=self.src_path,
            out_path=self._resource_path,
        )
        resource_builder = self.opts.get("build-resources", None)
        if resource_builder and not self._resource_spec:
            raise BuildException(
                f"Custom build-resources specified for {self.name} but no spec found"
            )
        if resource_builder:
            resource_builder = resource_builder.format(**context)
            self.echo("Running custom build-resources")
            ret = script(resource_builder, echo=self.echo)
            if not ret.ok:
                raise BuildException("Failed to build custom resources")

    def assemble_resources(self, artifact: Artifact, to_channels=("latest/edge",)):
        """Assemble charm's resources and associate in charmhub.

        Upload oci-images and any built-resource, gathering their revision
        Use the latest available for any other charm resource
        """
        context = dict(
            src_path=self.src_path,
            out_path=self._resource_path,
            arch=artifact.arch.value,
        )
        ch_channels = apply_channel_bounds(self.opts, to_channels)

        for name, details in self._read_metadata_resources(artifact).items():
            channel_range = ChannelRange()  # The resource is unbound by a charm channel
            if resource_fmt := self._resource_spec.get(name):
                if isinstance(resource_fmt, dict):
                    channel_range = ChannelRange.from_dict(resource_fmt)
                    resource_fmt = resource_fmt["format"]
            if not all(chan in channel_range for chan in ch_channels):
                self.echo(
                    f"Skipping resource {name} as at least one channel"
                    f"in {ch_channels} was out of the range of {channel_range}"
                )

            if not resource_fmt:
                # Reuse most recently uploaded resource
                self.echo(f"Reuse current resource {name} ...")
                revs = _CharmHub(self).resource_revisions(self.entity, name)
                resource = CharmResource(name, rev=revs[0]["Revision"])
            elif details["type"] == "oci-image":
                if upstream_source := details.get("upstream-source"):
                    # Pull any `upstream-image` annotated resources.
                    self.echo(
                        f"Pulling {upstream_source} for {artifact.series}/{artifact.arch}..."
                    )
                    docker = Docker(self)
                    docker.pull(upstream_source, platform=artifact.arch_docker)
                    # Use the local image-id from `docker images <upstream-source> -q`
                    resource_fmt = docker.images(upstream_source, "-q").strip()
                resource = CharmResource(name, ResourceKind.IMAGE, resource_fmt)
            elif details["type"] == "file":
                resource = CharmResource(
                    name, ResourceKind.FILEPATH, resource_fmt.format(**context)
                )
            artifact.resources.append(resource)

        for resource in artifact.resources:
            if resource.rev is None and resource.value:
                self.echo(f"Uploading resource:\n{pformat(resource)}")
                resource.rev = _CharmHub(self).upload_resource(self.entity, resource)

    def release(self, artifact: Artifact, to_channels=("edge",)):
        """Release charm and its resources to channels."""
        ch_channels = apply_channel_bounds(self.opts, to_channels)
        _CharmHub(self).release(self.entity, artifact, ch_channels)


class BundleBuildEntity(BuildEntity):
    """Overrides BuildEntity with bundle specific methods."""

    def __init__(self, *args, **kwargs):
        """Create a BuildEntity for Charm Bundles."""
        super().__init__(*args, **kwargs)
        self.type = "Bundle"
        self.src_path = str(self.opts["src_path"])

    def bundle_differs(self, artifact: Artifact):
        """Determine if this bundle has changes to include in a new push."""
        remote_bundle = self.download(None)
        if not remote_bundle:
            return True
        local_bundle = zipfile.ZipFile(artifact.charm_or_bundle)

        def _crc_list(bundle_zip):
            return sorted(
                [
                    (_.filename, _.CRC)
                    for _ in bundle_zip.infolist()
                    if _.filename != "manifest.yaml"
                ]
            )

        if _crc_list(remote_bundle) != _crc_list(local_bundle):
            self.echo("Local bundle differs.")
            return True

        self.echo(f"No differences found, not pushing new bundle {self.entity}")
        return False

    def bundle_build(self, to_channel):
        outputdir = Path(self.opts["dst_path"])
        if not self.opts.get("skip-build"):
            build = sh.Command(f"{self.src_path}/bundle")
            build(
                "-n",
                self.name,
                "-o",
                str(outputdir),
                "-c",
                to_channel,
                *self.opts["fragments"].split(),
                _tee=True,
                _out=self.echo,
            )
        else:
            # If we're not building the bundle from the repo, we have
            # to copy it to the expected output location instead.
            shutil.copytree(
                Path(self.src_path) / self.opts.get("subdir", ""), outputdir
            )

        # If we're building for charmhub, it needs to be packed
        charmcraft_yaml = outputdir / "charmcraft.yaml"
        if not charmcraft_yaml.exists():
            contents = {
                "type": "bundle",
                "parts": {
                    "bundle": {
                        "prime": [
                            str(_.relative_to(outputdir))
                            for _ in outputdir.glob("**/*")
                            if _.is_file()
                        ]
                    }
                },
            }
            with charmcraft_yaml.open("w") as fp:
                yaml.safe_dump(contents, fp)
        bundle_path = Charmcraft(self).pack(_cwd=outputdir)
        self.channel = to_channel
        self.artifacts.append(Artifact(bundle_path, Arch.ALL))

    def reset_artifacts(self):
        """Reset the artifacts in order to facilitate multiple bundle builds by the same entity."""

        def delete_file_or_dir(file_or_dir):
            try:
                file_or_dir.unlink(missing_ok=True)
            except IsADirectoryError:
                shutil.rmtree(file_or_dir)

        outputdir = Path(self.opts["dst_path"])
        self.channel = self.build.db["build_args"]["to_channel"]  # reset the channel
        delete_file_or_dir(outputdir)  # delete any unzipped bundle directory
        for each in self.artifacts:
            delete_file_or_dir(each.charm_or_bundle)  # delete any zip'd bundle file
        self.artifacts = []
