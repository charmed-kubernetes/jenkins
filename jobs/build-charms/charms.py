"""
charms.py - Interface to building and publishing charms

Make sure that charm environments variables are set appropriately

CHARM_BUILD_DIR, CHARM_LAYERS_DIR, CHARM_INTERFACES_DIR

See `charm build --help` for more information.

Usage:

  tox -e py36 -- python3 jobs/build-charms/charms.py build \
     --repo-path ../../layer-canal/ --out-path $HOME/charms/builds/canal

  tox -e py36 -- python3 jobs/build-charms/charms.py --help
"""

import os
from glob import glob
from pathlib import Path
from pprint import pformat
import click
import sh
import yaml
import time


class CharmEnv:
    """ Charm environment
    """

    def __init__(self):
        try:
            self.build_dir = Path(os.environ.get("CHARM_BUILD_DIR"))
            self.layers_dir = Path(os.environ.get("CHARM_LAYERS_DIR"))
            self.interfaces_dir = Path(os.environ.get("CHARM_INTERFACES_DIR"))
        except TypeError:
            raise SystemExit(
                "CHARM_BUILD_DIR, CHARM_LAYERS_DIR, CHARM_INTERFACES_DIR: "
                "Unable to find some or all of these charm build environment variables."
            )


@click.group()
def cli():
    pass


@cli.command()
@click.option("--layer-index", required=True, help="Charm layer index")
@click.option("--layers", required=True, help="list of layers in YAML format")
@click.option(
    "--git-branch", required=True, help="Branch of layer to reference", default="master"
)
@click.option(
    "--retries", default=15, required=True, help="how many retries to perform"
)
@click.option(
    "--timeout", default=60, required=True, help="timeout between retries in seconds"
)
def pull_source(layer_index, layers, git_branch, retries, timeout):
    charm_env = CharmEnv()
    layers = Path(layers)
    layers = yaml.safe_load(layers.read_text("utf8"))
    num_runs = 0
    for layer in layers:

        def download():
            for line in sh.charm(
                "pull-source", "-v", "-i", layer_index, layer, _iter=True
            ):
                click.echo(line.strip())

        try:
            num_runs += 1
            download()
        except sh.ErrorReturnCode_1 as e:
            click.echo(f"Problem: {e}, retrying [{num_runs}/{retries}]")
            if num_runs == retries:
                raise SystemExit(f"Could not download charm after {retries} retries.")
            time.sleep(timeout)
            download()
        ltype, name = layer.split(":")
        if ltype == "layer":
            sh.git.checkout('-f', git_branch, _cwd=str(charm_env.layers_dir / name))
        elif ltype == "interface":
            sh.git.checkout('-f', git_branch, _cwd=str(charm_env.interfaces_dir / name))
        else:
            raise SystemExit(f"Unknown layer/interface: {layer}")


@cli.command()
@click.option("--repo-path", required=True, help="Path of charm vcs repo")
@click.option("--out-path", required=True, help="Path of built charm")
@click.option(
    "--git-branch",
    required=True,
    help="Git branch to build charm from",
    default="master",
)
def build(repo_path, out_path, git_branch):
    for line in sh.charm.build(
        r=True, force=True, _cwd=repo_path, _iter=True, _err_to_out=True
    ):
        click.echo(line.strip())
    sh.charm.proof(_cwd=out_path)


@cli.command()
@click.option("--repo-path", required=True, help="Path of charm vcs repo")
@click.option("--out-path", required=True, help="Path of built charm")
@click.option(
    "--charm-entity",
    required=True,
    help="Charm entity path (ie. cs~containers/flannel)",
)
def push(repo_path, out_path, charm_entity):
    git_commit = sh.git("rev-parse", "HEAD", _cwd=repo_path)
    git_commit = git_commit.stdout.decode().strip()
    click.echo("Grabbing git revision {}".format(git_commit))

    # Build a list of `oci-image` resources that have `upstream-source` defined,
    # which is added for this logic to work.
    resources = yaml.safe_load(
        Path(out_path).joinpath("metadata.yaml").read_text()
    ).get("resources", {})
    images = {
        name: details["upstream-source"]
        for name, details in resources.items()
        if details["type"] == "oci-image" and details.get("upstream-source")
    }

    click.echo(f"Found {len(images)} oci-image resources:\n{pformat(images)}\n")

    for image in images.values():
        click.echo(f"Pulling {image}...")
        sh.docker.pull(image)

    # Convert the image names and tags to `--resource foo=bar` format
    # for passing to `charm push`.
    resource_args = [
        arg
        for name, image in images.items()
        for arg in ("--resource", f"{name}={image}")
    ]

    out = sh.charm.push(out_path, charm_entity, *resource_args)
    click.echo(f"Charm push returned: {out}")
    # Output includes lots of ansi escape sequences from the docker push,
    # and we only care about the first line, which contains the url as yaml.
    out = yaml.safe_load(out.stdout.decode().strip().splitlines()[0])
    click.echo("Setting {} metadata: {}".format(out["url"], git_commit))
    sh.charm.set(out["url"], "commit={}".format(git_commit))


@cli.command()
@click.option(
    "--charm-entity",
    required=True,
    help="Charmstore entity id (ie. cs~containers/flannel)",
)
@click.option("--channel", required=True, help="Charm channel to display info from")
def show(charm_entity, channel):
    click.echo()
    click.echo(sh.charm.show(charm_entity, channel=channel))


@cli.command()
@click.option(
    "--charm-entity",
    required=True,
    help="Charmstore entity id (ie. cs~containers/flannel)",
)
@click.option("--from-channel", required=True, help="Charm channel to publish from")
@click.option("--to-channel", required=True, help="Charm channel to publish to")
def promote(charm_entity, from_channel, to_channel):
    charm_id = sh.charm.show(charm_entity, "--channel", from_channel, "id")
    charm_id = yaml.safe_load(charm_id.stdout.decode())
    resources_args = []
    try:
        resources = sh.charm(
            "list-resources", charm_id["id"]["Id"], channel=from_channel, format="yaml"
        )
        resources = yaml.safe_load(resources.stdout.decode())
        if resources:
            resources_args = [
                ("--resource", "{}-{}".format(resource["name"], resource["revision"]))
                for resource in resources
            ]
    except sh.ErrorReturnCode_1:
        click.echo("No resources for {}".format(charm_id))
    sh.charm.release(charm_id["id"]["Id"], "--channel", to_channel, *resources_args)


@cli.command()
@click.option(
    "--charm-entity",
    required=True,
    help="Charmstore entity id (ie. cs~containers/flannel)",
)
@click.option(
    "--channel",
    required=True,
    default="unpublished",
    help="Charm channel to query entity",
)
@click.option("--builder", required=True, help="Path of resource builder")
@click.option(
    "--out-path", required=True, help="Temporary storage of built charm resources"
)
@click.option(
    "--resource-spec", required=True, help="YAML Spec of resource keys and filenames"
)
def resource(charm_entity, channel, builder, out_path, resource_spec):
    out_path = Path(out_path)
    resource_spec = yaml.safe_load(Path(resource_spec).read_text())
    resource_spec_fragment = resource_spec.get(charm_entity, None)
    click.echo(resource_spec_fragment)
    if not resource_spec_fragment:
        raise SystemExit("Unable to determine resource spec for entity")

    os.makedirs(str(out_path), exist_ok=True)
    charm_id = sh.charm.show(charm_entity, "--channel", channel, "id")
    charm_id = yaml.safe_load(charm_id.stdout.decode())
    try:
        resources = sh.charm(
            "list-resources", charm_id["id"]["Id"], channel=channel, format="yaml"
        )
    except sh.ErrorReturnCode_1:
        click.echo("No resources found for {}".format(charm_id))
        return
    resources = yaml.safe_load(resources.stdout.decode())
    builder_sh = Path(builder).absolute()
    click.echo(builder_sh)
    for line in sh.bash(str(builder_sh), _cwd=out_path, _iter=True, _err_to_out=True):
        click.echo(line.strip())
    for line in glob("{}/*".format(out_path)):
        resource_path = Path(line)
        resource_fn = resource_path.parts[-1]
        resource_key = resource_spec_fragment.get(resource_fn, None)
        if resource_key:
            is_attached = False
            is_attached_count = 0
            while not is_attached:
                try:
                    out = sh.charm.attach(
                        charm_entity,
                        "--channel",
                        channel,
                        f"{resource_key}={resource_path}",
                        _err_to_out=True,
                    )
                    is_attached = True
                except sh.ErrorReturnCode_1 as e:
                    click.echo(f"Problem attaching resources, retrying: {e}")
                    is_attached_count += 1
                    if is_attached_count > 10:
                        raise SystemExit(
                            "Could not attach resource and max retry count reached."
                        )
            click.echo(out)


if __name__ == "__main__":
    cli()
