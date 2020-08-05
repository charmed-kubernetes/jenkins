""" Charm build interfaces
"""
from cilib.run import cmd_ok
from enum import Enum
from pathlib import Path
from pathos.threading import ThreadPool
import click
import os
import yaml


class BuildException(Exception):
    pass


class BuildType(Enum):
    CHARM = 1
    BUNDLE = 2


class LayerType(Enum):
    LAYER = 1
    INTERFACE = 2


class Environment:
    """ Environment setup class

    This will provide methods for setting up a build environment by downloading
    and caching any layers and interfaces needed for reactive style charms. This
    is always done regardless of if we're building ops framework style charms
    using charmcraft which will just bypass this information all together.
    """

    try:
        build_dir = Path(os.environ.get("CHARM_BUILD_DIR"))
        layers_dir = Path(os.environ.get("CHARM_LAYERS_DIR"))
        interfaces_dir = Path(os.environ.get("CHARM_INTERFACES_DIR"))
        tmp_dir = Path(os.environ.get("WORKSPACE"))
    except TypeError:
        raise BuildException(
            "CHARM_BUILD_DIR, CHARM_LAYERS_DIR, CHARM_INTERFACES_DIR, WORKSPACE: "
            "Unable to find some or all of these charm build environment variables."
        )

    def __init__(self):
        self.db = {}

    @property
    def layers(self):
        """ List of layers defined in our jobs/includes/charm-layer-list.inc
        """
        return yaml.safe_load(
            Path(self.db["build_args"]["layer_list"]).read_text(encoding="utf8")
        )

    @property
    def artifacts(self):
        """ List of charms or bundles to process
        """
        return yaml.safe_load(
            Path(self.db["build_args"]["artifact_list"]).read_text(encoding="utf8")
        )

    @property
    def layer_index(self):
        """ Remote Layer index
        """
        return self.db["build_args"].get("layer_index", None)

    @property
    def layer_branch(self):
        """ Remote Layer branch
        """
        return self.db["build_args"].get("layer_branch", None)

    @property
    def filter_by_tag(self):
        """ filter tag
        """
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
    def rebuild_cache(self):
        return self.db["build_args"].get("rebuild_cache", None)

    @property
    def force(self):
        return self.db["build_args"].get("force", None)

    def _layer_type(self, ltype):
        """ Check the type of an individual layer set in the layer list
        """
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
        if Path(self.build_path(layer_name)).exists():
            click.echo(f"- Refreshing {layer_name} cache.")
            cmd_ok(f"git checkout {self.layer_branch}", cwd=self.build_path(layer_name))
            cmd_ok(
                f"git pull origin {self.layer_branch}", cwd=self.build_path(layer_name),
            )
        else:
            click.echo(f"- Downloading {layer_name}")
            cmd_ok(f"charm pull-source -i {self.layer_index} {layer_name}")
        return True

    def pull_layers(self):
        """ clone all downstream layers to be processed locally when doing charm builds
        """
        if self.rebuild_cache:
            click.echo("-  rebuild cache triggered, cleaning out cache.")
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
        pool.map(self.download, layers_to_pull)

        self.db["pull_layer_manifest"] = []
        _paths_to_process = {
            "layer": glob("{}/*".format(str(self.layers_dir))),
            "interface": glob("{}/*".format(str(self.interfaces_dir))),
        }
        for prefix, paths in _paths_to_process.items():
            for _path in paths:
                build_path = _path
                if not build_path:
                    raise BuildException(f"Could not determine build path for {_path}")

                ret = cmd_ok(f"git checkout {self.layer_branch}", _cwd=build_path)
                if not ret.ok:
                    raise BuildException(
                        f"Could find {self.layer_branch} branch for layer: {build_path}"
                    )


class BuildEntity:
    """ The Build data class
    """

    def __init__(self, build_env, name, opts):
        self.build = build_env
        # Bundle or charm name
        self.name = name

        # Alias to name
        self.src_path = self.name

        # Bundle or charm opts as defined in the layer include
        self.opts = opts

    def setup(self):
        """ Setup directory for charm build
        """
        downstream = f"https://github.com/{self.opts['downstream']}"
        click.echo(f"Cloning repo from {downstream}")

        os.makedirs(self.src_path)
        cmd_ok(
            f"git clone --branch {self.build.db['build_args']['charm_branch']} "
            "{downstream} {self.src_path}"
        )

    def build(self):
        """ Perform charm build against charm/bundle
        """
        ret = cmd_ok("make charm", cwd=self.src_path)
        if not ret.ok:
            # Until https://github.com/juju/charm-tools/pull/554 is fixed.
            click.echo("Ignoring proof warning")

    def push(self, namespace, channel):
        """ Pushes a built charm to Charmstore
        """
        cmd_ok(f"make NAMESPACE={namespace} CHANNEL={channel} upload")
