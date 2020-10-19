"""
charms.py - Interface to building and publishing charms

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
from pathlib import Path
from sh.contrib import git
from cilib.service.aws import Store
from cilib.run import cmd_ok, capture, script
from datetime import datetime
from enum import Enum
from retry.api import retry_call
from subprocess import CalledProcessError
from types import SimpleNamespace
from pathos.threading import ThreadPool
import click
import shutil
import sh
import yaml
import json
import requests
import re


class BuildException(Exception):
    pass


class BuildType(Enum):
    CHARM = 1
    BUNDLE = 2


class LayerType(Enum):
    LAYER = 1
    INTERFACE = 2


class BuildEnv:
    """Charm or Bundle build data class"""

    try:
        build_dir = Path(os.environ.get("CHARM_BUILD_DIR"))
        layers_dir = Path(os.environ.get("CHARM_LAYERS_DIR"))
        interfaces_dir = Path(os.environ.get("CHARM_INTERFACES_DIR"))
        tmp_dir = Path(os.environ.get("WORKSPACE"))
        home_dir = Path(os.environ.get("HOME"))
    except TypeError:
        raise BuildException(
            "CHARM_BUILD_DIR, CHARM_LAYERS_DIR, CHARM_INTERFACES_DIR, WORKSPACE, HOME: "
            "Unable to find some or all of these charm build environment variables."
        )

    def __init__(self, build_type):
        self.store = Store("BuildCharms")
        self.now = datetime.utcnow()
        self.build_type = build_type
        self.db = {}

        if self.build_type == BuildType.CHARM:
            self.db_json = Path("buildcharms.json")
        elif self.build_type == BuildType.BUNDLE:
            self.db_json = Path("buildbundles.json")

        if not self.db.get("build_datetime", None):
            self.db["build_datetime"] = self.now.strftime("%Y/%m/%d")

        # Reload data from current day
        response = self.store.get_item(
            Key={"build_datetime": self.db["build_datetime"]}
        )
        if response and "Item" in response:
            self.db = response["Item"]

    @property
    def layers(self):
        """List of layers defined in our jobs/includes/charm-layer-list.inc"""
        return yaml.safe_load(
            Path(self.db["build_args"]["layer_list"]).read_text(encoding="utf8")
        )

    @property
    def artifacts(self):
        """List of charms or bundles to process"""
        return yaml.safe_load(
            Path(self.db["build_args"]["artifact_list"]).read_text(encoding="utf8")
        )

    @property
    def layer_index(self):
        """Remote Layer index"""
        return self.db["build_args"].get("layer_index", None)

    @property
    def layer_branch(self):
        """Remote Layer branch"""
        return self.db["build_args"].get("layer_branch", None)

    @property
    def filter_by_tag(self):
        """filter tag"""
        return self.db["build_args"].get("filter_by_tag", None)

    @property
    def resource_spec(self):
        return self.db["build_args"].get("resource_spec", None)

    @property
    def to_channel(self):
        return self.db["build_args"].get("to_channel", None)

    @property
    def from_channel(self):
        return self.db["build_args"].get("from_channel", None)

    @property
    def force(self):
        return self.db["build_args"].get("force", None)

    def _layer_type(self, ltype):
        """Check the type of an individual layer set in the layer list"""
        if ltype == "layer":
            return LayerType.LAYER
        elif ltype == "interface":
            return LayerType.INTERFACE
        raise BuildException(f"Unknown layer type for {ltype}")

    def build_path(self, layer):
        ltype, name = layer.split(":")
        if self._layer_type(ltype) == LayerType.LAYER:
            return str(self.layers_dir / name)
        elif self._layer_type(ltype) == LayerType.INTERFACE:
            return str(self.interfaces_dir / name)
        else:
            return None

    def save(self):
        click.echo("Saving build")
        click.echo(dict(self.db))
        self.db_json.write_text(json.dumps(dict(self.db)))
        self.store.put_item(Item=dict(self.db))

    def promote_all(self, from_channel="unpublished", to_channel="edge"):
        for charm_map in self.artifacts:
            for charm_name, charm_opts in charm_map.items():
                if not any(match in self.filter_by_tag for match in charm_opts["tags"]):
                    continue

                charm_entity = f"cs:~{charm_opts['namespace']}/{charm_name}"
                click.echo(
                    f"Promoting :: {charm_entity:^35} :: from:{from_channel} to: {to_channel}"
                )
                charm_id = sh.charm.show(charm_entity, "--channel", from_channel, "id")
                charm_id = yaml.safe_load(charm_id.stdout.decode())
                resources_args = []
                try:
                    resources = sh.charm(
                        "list-resources",
                        charm_id["id"]["Id"],
                        channel=from_channel,
                        format="yaml",
                    )
                    resources = yaml.safe_load(resources.stdout.decode())
                    if resources:
                        resources_args = [
                            (
                                "--resource",
                                "{}-{}".format(resource["name"], resource["revision"]),
                            )
                            for resource in resources
                        ]
                except sh.ErrorReturnCode_1:
                    click.echo("No resources for {}".format(charm_id))
                sh.charm.release(
                    charm_id["id"]["Id"], "--channel", to_channel, *resources_args
                )

    def download(self, layer_name):
        out = capture(
            f"charm pull-source -i {self.layer_index} -b {self.layer_branch} {layer_name}"
        )
        click.echo(f"-  {out.stdout.decode()}")
        rev = re.compile("rev: ([a-zA-Z0-9]+)")
        layer_manifest = {
            "rev": rev.search(out.stdout.decode()).group(1),
            "url": layer_name,
        }
        return layer_manifest

    def pull_layers(self):
        """clone all downstream layers to be processed locally when doing charm builds"""
        shutil.rmtree(str(self.build_dir))
        shutil.rmtree(str(self.layers_dir))
        shutil.rmtree(str(self.interfaces_dir))
        os.mkdir(str(self.layers_dir))
        os.mkdir(str(self.interfaces_dir))

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
    """The Build data class"""

    def __init__(self, build, name, opts, entity):
        # Build env
        self.build = build

        # Bundle or charm name
        self.name = name

        src_path = Path(self.name).absolute()
        self.layer_path = src_path / "layer.yaml"
        self.legacy_charm = False

        self.src_path = str(src_path)
        self.dst_path = str(self.build.build_dir / self.name)

        # Bundle or charm opts as defined in the layer include
        self.opts = opts

        self.namespace = opts["namespace"]

        # Entity path, ie cs:~containers/kubernetes-master
        self.entity = entity

        # Entity path with current revision (from target channel)
        self.full_entity = self.get_charmstore_rev_url()

        # Entity path with new revision (from pushing)
        self.new_entity = None

    def __str__(self):
        return f"<BuildEntity: {self.name} ({self.full_entity}) (legacy charm: {self.legacy_charm})>"

    def get_charmstore_rev_url(self):
        # Grab charmstore revision for channels charm
        response = capture(
            [
                "charm",
                "show",
                self.entity,
                "--channel",
                self.build.db["build_args"]["to_channel"],
                "id",
            ]
        )
        if not response.ok:
            return None
        response = yaml.safe_load(response.stdout.decode().strip())
        return response["id"]["Id"]

    def download(self, fname):
        if not self.full_entity:
            return SimpleNamespace(ok=False)
        entity_p = self.full_entity.lstrip("cs:")
        url = f"https://api.jujucharms.com/charmstore/v5/{entity_p}/archive/{fname}"
        click.echo(f"Downloading {fname} from {url}")
        return requests.get(url)

    @property
    def has_changed(self):
        """Determine if the charm/layers commits have changed since last publish to charmstore"""
        if not self.legacy_charm:
            # Operator framework charms won't have a .build.manifest and it's
            # sufficient to just compare the charm repo's commit rev.
            extra_info = yaml.safe_load(
                sh.charm(
                    "show",
                    self.full_entity,
                    "extra-info",
                    format="yaml",
                ).stdout.decode()
            )
            old_commit = extra_info.get("commit")
            new_commit = self.commit
            changed = new_commit != new_commit
            if changed:
                click.echo(f"Changes found: {new_commit} (new) != {old_commit} (old)")
            return changed

        charmstore_build_manifest = None
        resp = self.download(".build.manifest")
        if resp.ok:
            charmstore_build_manifest = resp.json()

        if not charmstore_build_manifest:
            click.echo(
                "No build.manifest located, unable to determine if any changes occurred."
            )
            return True

        current_build_manifest = [
            {"rev": curr["rev"], "url": curr["url"]}
            for curr in self.build.db["pull_layer_manifest"]
        ]

        # Check the current git cloned charm repo commit and add that to
        # current pull-layer-manifest as that would no be known at the
        # time of pull_layers
        current_build_manifest.append({"rev": self.commit, "url": self.name})

        the_diff = [
            i
            for i in charmstore_build_manifest["layers"]
            if i not in current_build_manifest
        ]
        if the_diff:
            click.echo("Changes found:")
            click.echo(the_diff)
            return True
        click.echo(f"No changes found, not building a new {self.entity}")
        return False

    @property
    def commit(self):
        """Commit hash of downstream repo"""
        if not Path(self.src_path).exists():
            raise BuildException(f"Could not locate {self.src_path}")

        git_commit = git("rev-parse", "HEAD", _cwd=self.src_path)
        return git_commit.stdout.decode().strip()

    def _read_metadata_resources(self):
        if self.legacy_charm:
            # Legacy (reactive) charms can have resources added by layers,
            # so we need to read from the built charm.
            metadata_path = Path(self.dst_path) / "metadata.yaml"
        else:
            metadata_path = Path(self.src_path) / "metadata.yaml"
        metadata = yaml.safe_load(metadata_path.read_text())
        return metadata.get("resources", {})

    def setup(self):
        """Setup directory for charm build"""
        downstream = f"https://github.com/{self.opts['downstream']}"
        click.echo(f"Cloning repo from {downstream}")

        os.makedirs(self.src_path)
        for line in git.clone(
            "--branch",
            self.build.db["build_args"]["charm_branch"],
            downstream,
            self.src_path,
            _iter=True,
            _bg_exc=False,
        ):
            click.echo(line)

        self.legacy_charm = self.layer_path.exists()
        if not self.legacy_charm:
            self.dst_path += ".charm"

    def charm_build(self):
        """Perform charm build against charm/bundle"""
        if "override-build" in self.opts:
            click.echo("Override build found, running in place of charm build.")
            ret = script(
                self.opts["override-build"], cwd=self.src_path, charm=self.name
            )
        elif self.legacy_charm:
            ret = cmd_ok(
                "charm build -r --force -i https://localhost",
                cwd=self.src_path,
            )
        else:
            ret = cmd_ok(
                f"charmcraft build -f {self.src_path}",
                cwd=self.build.build_dir,
            )

        if not ret.ok:
            raise SystemExit(f"Failed to build {self.name}")

    def push(self):
        """Pushes a built charm to Charmstore"""

        if "override-push" in self.opts:
            click.echo("Override push found, running in place of charm push.")
            script(
                self.opts["override-push"],
                cwd=self.src_path,
                charm=self.name,
                namespace=self.namespace,
            )
            return

        click.echo(f"Pushing built {self.dst_path} to {self.entity}")

        out = retry_call(
            capture,
            fargs=[["charm", "push", self.dst_path, self.entity]],
            fkwargs={"check": True},
            delay=2,
            backoff=2,
            exceptions=CalledProcessError,
        )
        click.echo(f"Charm push returned: {out}")
        # Output includes lots of ansi escape sequences from the docker push,
        # and we only care about the first line, which contains the url as yaml.
        out = yaml.safe_load(out.stdout.decode().strip().splitlines()[0])
        self.new_entity = out["url"]
        click.echo(f"Setting {self.new_entity} metadata: {self.commit}")
        cmd_ok(["charm", "set", self.new_entity, f"commit={self.commit}"])

    def attach_resources(self):
        out_path = Path(self.src_path) / "tmp"
        os.makedirs(str(out_path), exist_ok=True)
        resource_spec = yaml.safe_load(Path(self.build.resource_spec).read_text())
        resources = resource_spec.get(self.entity, {})

        # Build any custom resources.
        resource_builder = self.opts.get("build-resources", None)
        if resource_builder and not resources:
            raise SystemExit(
                "Custom build-resources specified for {self.entity} but no spec found"
            )
        if resource_builder:
            resource_builder = resource_builder.format(
                out_path=out_path,
                src_path=self.src_path,
            )
            click.echo("Running custom build-resources")
            ret = script(resource_builder)
            if not ret.ok:
                raise SystemExit("Failed to build custom resources")

        # Pull any `upstream-image` annotated resources.
        resources = self._read_metadata_resources()
        for name, details in resources.items():
            upstream_image = details.get("upstream-source")
            if details["type"] == "oci-image" and upstream_image:
                click.echo(f"Pulling {upstream_image}...")
                sh.docker.pull(upstream_image)
                resources[name] = upstream_image

        # Attach all resources.
        for name, resource in resources.items():
            # If the resource is a file, populate the path where it was built.
            # If it's a custom image, it will be in Docker and this will be a no-op.
            resource = resource.format(out_path=out_path)
            click.echo(f"Attaching {name}={resource}")
            retry_call(
                cmd_ok,
                fargs=[
                    [
                        "charm",
                        "attach",
                        self.new_entity,
                        f"{name}={resource}",
                    ]
                ],
                fkwargs={"check": True},
                delay=2,
                backoff=2,
                tries=15,
                exceptions=CalledProcessError,
            )

    def promote(self, from_channel="unpublished", to_channel="edge"):
        click.echo(
            f"Promoting :: {self.entity:^35} :: from:{from_channel} to: {to_channel}"
        )
        charm_id = sh.charm.show(self.entity, "--channel", from_channel, "id")
        charm_id = yaml.safe_load(charm_id.stdout.decode())
        resources_args = []
        try:
            resources = sh.charm(
                "list-resources",
                charm_id["id"]["Id"],
                channel=from_channel,
                format="yaml",
            )
            resources = yaml.safe_load(resources.stdout.decode())
            if resources:
                resources_args = [
                    (
                        "--resource",
                        "{}-{}".format(resource["name"], resource["revision"]),
                    )
                    for resource in resources
                ]
        except sh.ErrorReturnCode:
            click.echo("No resources for {}".format(charm_id))
        sh.charm.release(charm_id["id"]["Id"], "--channel", to_channel, *resources_args)


class BundleBuildEntity(BuildEntity):
    def push(self):
        """Pushes a built charm to Charmstore"""

        click.echo(f"Pushing bundle {self.name} from {self.src_path} to {self.entity}")
        out = sh.charm.push(self.src_path, self.entity)
        click.echo(f"Charm push returned: {out}")
        # Output includes lots of ansi escape sequences from the docker push,
        # and we only care about the first line, which contains the url as yaml.
        out = yaml.safe_load(out.stdout.decode().strip().splitlines()[0])
        click.echo(f"Setting {out['url']} metadata: {self.commit}")
        sh.charm.set(out["url"], f"commit={self.commit}", _bg_exc=False)

    @property
    def has_changed(self):
        charmstore_bundle = self.download("bundle.yaml")
        charmstore_bundle = yaml.safe_load(charmstore_bundle.text)
        charmstore_bundle_services = charmstore_bundle.get(
            "applications", charmstore_bundle.get("services", {})
        )

        local_built_bundle = yaml.safe_load(
            (Path(self.name) / "bundle.yaml").read_text(encoding="utf8")
        )
        local_built_bundle_services = local_built_bundle.get(
            "applications", local_built_bundle.get("services", {})
        )
        the_diff = [
            i["charm"]
            for _, i in charmstore_bundle_services.items()
            if i["charm"] not in local_built_bundle_services
        ]
        if the_diff:
            click.echo("Changes found:")
            click.echo(the_diff)
            return True

        click.echo(f"No charm changes found, not pushing new bundle {self.entity}")
        return False


@click.group()
def cli():
    pass


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
    to_channel,
    force,
):
    build_env = BuildEnv(build_type=BuildType.CHARM)
    build_env.db["build_args"] = {
        "artifact_list": charm_list,
        "layer_list": layer_list,
        "layer_index": layer_index,
        "charm_branch": charm_branch,
        "layer_branch": layer_branch,
        "resource_spec": resource_spec,
        "filter_by_tag": list(filter_by_tag),
        "to_channel": to_channel,
        "force": force,
    }

    build_env.pull_layers()

    entities = []
    for charm_map in build_env.artifacts:
        for charm_name, charm_opts in charm_map.items():
            if not any(match in filter_by_tag for match in charm_opts["tags"]):
                continue

            charm_entity = f"cs:~{charm_opts['namespace']}/{charm_name}"
            entities.append(
                BuildEntity(build_env, charm_name, charm_opts, charm_entity)
            )
            click.echo(f"Queued {charm_entity} for building")

    def _run_build(entity):
        entity.setup()

        if not entity.has_changed and not build_env.force:
            return

        click.echo(f"Processing: {entity}")
        entity.charm_build()

        entity.push()
        entity.attach_resources()
        entity.promote(to_channel=to_channel)

    pool = ThreadPool()
    pool.map(_run_build, entities)
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
    "--to-channel", required=True, help="channel to promote bundle to", default="edge"
)
def build_bundles(bundle_list, bundle_branch, filter_by_tag, bundle_repo, to_channel):
    build_env = BuildEnv(build_type=BuildType.BUNDLE)
    build_env.db["build_args"] = {
        "artifact_list": bundle_list,
        "bundle_branch": bundle_branch,
        "filter_by_tag": list(filter_by_tag),
        "to_channel": to_channel,
    }

    default_repo_dir = build_env.tmp_dir / "bundles-kubernetes"
    # bundle_build_dir = build_env.tmp_dir / "tmp-bundles"
    # sh.rm("-rf", bundle_repo_dir)
    # sh.rm("-rf", bundle_build_dir)
    # os.makedirs(str(bundle_repo_dir), exist_ok=True)
    # os.makedirs(str(bundle_build_dir), exist_ok=True)
    for line in git.clone(
        "--branch",
        bundle_branch,
        bundle_repo,
        str(default_repo_dir),
        _iter=True,
        _bg_exc=False,
    ):
        click.echo(line)

    for bundle_map in build_env.artifacts:
        for bundle_name, bundle_opts in bundle_map.items():
            if not any(match in filter_by_tag for match in bundle_opts["tags"]):
                click.echo(f"Skipping {bundle_name}")
                continue
            click.echo(f"Processing {bundle_name}")
            if "repo" in bundle_opts:
                # override bundle repo
                bundle_repo_dir = build_env.tmp_dir / bundle_name
                for line in git.clone(
                    "--branch",
                    bundle_branch,
                    bundle_opts["repo"],
                    str(bundle_repo_dir),
                    _iter=True,
                    _bg_exc=False,
                ):
                    click.echo(line)
            else:
                bundle_repo_dir = default_repo_dir

            if not bundle_opts.get("skip-build", False):
                cmd = [
                    str(bundle_repo_dir / "bundle"),
                    "-o",
                    bundle_name,
                    "-c",
                    to_channel,
                    bundle_opts["fragments"],
                ]
                click.echo(f"Running {' '.join(cmd)}")
                import subprocess

                subprocess.run(" ".join(cmd), shell=True)
            else:
                # If we're not building the bundle from the repo, we have
                # to copy it to the expected output location instead.
                bundle_path = bundle_repo_dir / bundle_opts.get("subdir", "")
                Path(bundle_name).mkdir()
                shutil.copytree(bundle_path, bundle_name)

            bundle_entity = f"cs:~{bundle_opts['namespace']}/{bundle_name}"
            build_entity = BundleBuildEntity(
                build_env, bundle_name, bundle_opts, bundle_entity
            )
            build_entity.push()
            build_entity.promote(to_channel=to_channel)

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
    build_env = BuildEnv(build_type=BuildType.CHARM)
    build_env.db["build_args"] = {
        "artifact_list": charm_list,
        "filter_by_tag": list(filter_by_tag),
        "to_channel": to_channel,
        "from_channel": from_channel,
    }
    return build_env.promote_all(from_channel=from_channel, to_channel=to_channel)


if __name__ == "__main__":
    cli()
