"""
snaps-eks.py - Interface for building and publishing snaps

"""

import sys
sys.path.insert(0, '.')

import click
import sh
import os
import glob
import re
import yaml
import operator
from sdk import snap as snapapi
from pathlib import Path


def _alias(match_re, rename_re, snap):
    """ Provide any snap substitutions for things like kubectl-eks...snap

    Usage:

      alias = _rename(match_re\'(?=\\S*[-]*)([a-zA-Z-]+)(.*)\',
                      rename-re=\'\\1-eks_\\2\',
                      snap=kubectl)
    """
    click.echo(f"Setting alias based on {match_re} -> {rename_re}: {snap}")
    return re.sub(match_re, fr"{rename_re}", snap)


def _set_snap_alias(build_path, alias):
    click.echo(f"Setting new snap alias: {alias}")
    if build_path.exists():
        snapcraft_yml = yaml.load(build_path.read_text())
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
    "--build-path", required=True, default="release/snap", help="Path of snap builds"
)
@click.option("--version", required=True, help="Version of k8s to build")
@click.option(
    "--arch", required=True, default="amd64", help="Architecture to build against"
)
@click.option("--match-re", default="(?=\S*[-]*)([a-zA-Z-]+)(.*)", help="Regex matcher")
@click.option("--rename-re", help="Regex renamer, ie \1-eks")
@click.option("--dry-run", is_flag=True)
def build(snap, build_path, version, arch, match_re, rename_re, dry_run):
    """ Build snaps

    Usage:

    snaps.py build --snap kubectl --snap kube-proxy --version 1.10.3 --arch amd64 --match-re '(?=\S*[-]*)([a-zA-Z-]+)(.*)' --rename-re '\1-eks'

    Passing --rename-re and --match-re allows you to manipulate the resulting
    snap file, for example, the above renames kube-proxy_1.10.3_amd64.snap to
    kube-proxy-eks_1.10.3_amd64.snap
    """
    if not version.startswith("v"):
        version = f"v{version}"
    env = os.environ.copy()
    env["KUBE_VERSION"] = version
    env["KUBE_ARCH"] = arch
    sh.git.clone(
        "https://github.com/juju-solutions/release.git",
        build_path,
        branch="rye/snaps",
        depth="1",
    )
    build_path = Path(build_path) / "snap"
    snap_alias = None

    for _snap in snap:
        if match_re and rename_re:
            snap_alias = _alias(match_re, rename_re, _snap)

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
                _iter=True,
                _err_to_out=True,
            ):
                click.echo(line.strip())


@cli.command()
@click.option(
    "--result-dir",
    required=True,
    default="release/snap/build",
    help="Path of resulting snap builds",
)
@click.option("--dry-run", is_flag=True)
def push(result_dir, dry_run):
    """ Promote to a snapstore channel/track

    Usage:

       tox -e py36 -- python3 snaps.py push --result-dir ./release/snap/build
    """
    # TODO: Verify channel is a ver/chan string
    #   re: [\d+\.]+\/(?:edge|stable|candidate|beta)
    for fname in glob.glob(f"{result_dir}/*.snap"):
        try:
            click.echo(f"Running: snapcraft push {fname}")
            if dry_run:
                click.echo("dry-run only:")
                click.echo(f"  > snapcraft push {fname}")
            else:
                for line in sh.snapcraft.push(fname, _iter=True, _err_to_out=True):
                    click.echo(line.strip())
        except sh.ErrorReturnCode_2 as e:
            click.echo("Failed to upload to snap store")
            click.echo(e.stdout)
            click.echo(e.stderr)
        except sh.ErrorReturnCode_1 as e:
            click.echo("Failed to upload to snap store")
            click.echo(e.stdout)
            click.echo(e.stderr)


@cli.command()
@click.option("--name", required=True, help="Snap name to release")
@click.option("--channel", required=True, help="Snapstore channel to release to")
@click.option("--version", required=True, help="Snap application version to release")
@click.option("--dry-run", is_flag=True)
def release(name, channel, version, dry_run):
    """ Release the most current revision snap to channel
    """
    latest_release = snapapi.latest(name, version)
    click.echo(latest_release)
    if dry_run:
        click.echo("dry-run only:")
        click.echo(f"  > snapcraft release {name} {latest_release['rev']} {channel}")
    else:
        click.echo(
            sh.snapcraft.release(name, latest_release["rev"], channel, _err_to_out=True)
        )


if __name__ == "__main__":
    cli()
