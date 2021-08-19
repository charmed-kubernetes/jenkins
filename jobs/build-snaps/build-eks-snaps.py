"""
Interface for building and publishing snaps

"""

import click
import sh
import os
import glob
import yaml
from pathlib import Path
from sh.contrib import git


def _set_snap_alias(build_path, alias):
    click.echo(f"Setting new snap alias: {alias}")
    if build_path.exists():
        snapcraft_yml = yaml.safe_load(build_path.read_text())
        if snapcraft_yml["name"] != alias:
            snapcraft_yml["name"] = alias
            build_path.write_text(
                yaml.dump(snapcraft_yml, default_flow_style=False, indent=2)
            )


@click.group()
def cli():
    pass


@cli.command()
@click.option("--snap", required=True, multiple=True, help="Snaps to build")
@click.option(
    "--version", required=True, default="1.21.1", help="Version of k8s to build"
)
@click.option(
    "--arch", required=True, default="amd64", help="Architecture to build against"
)
@click.option("--dry-run", is_flag=True)
def build(snap, version, arch, dry_run):
    """ Build snaps

    Usage:

    build-eks-snaps.py build \
        --snap kubectl \
        --snap kube-proxy \
        --snap kubelet \
        --snap kubernetes-test \
        --version 1.21.1
    """
    if not version.startswith("v"):
        version = f"v{version}"
    env = os.environ.copy()
    env["KUBE_VERSION"] = version
    env["KUBE_ARCH"] = arch
    git.clone(
        "https://github.com/juju-solutions/release.git",
        "release",
        branch="rye/snaps",
        depth="1",
    )
    build_path = Path("release/snap")
    snap_alias = None

    for _snap in snap:
        snap_alias = f"{_snap}-eks"

        if snap_alias:
            snapcraft_fn = build_path / f"{_snap}.yaml"
            _set_snap_alias(snapcraft_fn, snap_alias)

        if dry_run:
            click.echo("dry-run only:")
            click.echo(
                f"  > cd release/snap && bash build-scripts/docker-build {_snap}"
            )
        else:
            for line in sh.bash(
                "build-scripts/docker-build",
                _snap,
                _env=env,
                _cwd=str(build_path),
                _bg_exc=False,
                _iter=True,
            ):
                click.echo(line.strip())


@cli.command()
@click.option(
    "--result-dir",
    required=True,
    default="release/snap/build",
    help="Path of resulting snap builds",
)
@click.option("--version", required=True, default="1.21.1", help="k8s Version")
@click.option("--dry-run", is_flag=True)
def push(result_dir, version, dry_run):
    """Promote to a snapstore channel/track"""
    for fname in glob.glob(f"{result_dir}/*.snap"):
        try:
            click.echo(f"Running: snapcraft upload {fname}")
            if dry_run:
                click.echo("dry-run only:")
                click.echo(f"  > snapcraft upload {fname}")
            else:
                for line in sh.snapcraft.upload(
                    fname,
                    "--release",
                    f"{version}/edge,{version}/beta,{version}/candidate,{version}/stable",
                    _iter=True,
                    _bg_exc=False,
                ):
                    click.echo(line.strip())
        except sh.ErrorReturnCode as e:
            click.echo("Failed to upload to snap store")
            click.echo(e.stdout)
            click.echo(e.stderr)


if __name__ == "__main__":
    cli()
