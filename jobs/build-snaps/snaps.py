"""
snaps.py - Interface for building and publishing snaps

"""

import click
import sh
import os
import glob
import re
import yaml
from pathlib import Path


def _alias(match_re, rename_re, snap):
    """ Provide any snap substitutions for things like kubectl-eks...snap

    Usage:

      alias = _rename(match_re\'(?=\\S*[-]*)([a-zA-Z-]+)(.*)\',
                      rename-re=\'\\1-eks_\\2\',
                      snap=kubectl)
    """
    click.echo(f'Setting alias based on {match_re} -> {rename_re}: {snap}')
    return re.sub(match_re, fr'{rename_re}', snap)

def _set_snap_alias(build_path, alias):
    click.echo(f'Setting new snap alias: {alias}')
    if build_path.exists():
        snapcraft_yml = yaml.load(build_path.read_text())
        if snapcraft_yml['name'] != alias:
            snapcraft_yml['name'] = alias
            build_path.write_text(yaml.dump(snapcraft_yml,
                                            default_flow_style=False,
                                            indent=2))

@click.group()
def cli():
    pass

@cli.command()
@click.option('--snap', required=True, multiple=True, help='Snaps to build')
@click.option('--version', required=True, help='Version of k8s to build')
@click.option('--arch', required=True, default='amd64', help='Architecture to build against')
@click.option('--match-re', default='(?=\S*[-]*)([a-zA-Z-]+)(.*)', help='Regex matcher')
@click.option('--rename-re', help='Regex renamer, ie \1-eks')
def build(snap, version, arch, match_re, rename_re):
    """ Build snaps

    Usage:

    snaps.py build --snap kubectl --snap kube-proxy --version 1.10.3 --arch amd64 --match-re '(?=\S*[-]*)([a-zA-Z-]+)(.*)' --rename-re '\1-eks'

    Passing --rename-re and --match-re allows you to manipulate the resulting
    snap file, for example, the above renames kube-proxy_1.10.3_amd64.snap to
    kube-proxy-eks_1.10.3_amd64.snap
    """
    if not version.startswith('v'):
        version = f'v{version}'
    env = os.environ.copy()
    env['KUBE_VERSION'] = version
    env['KUBE_ARCH'] = arch
    sh.git.clone('https://github.com/juju-solutions/release.git',
                 branch='rye/snaps', depth='1')
    build_path = Path('release/snap')
    snap_alias = None
    for _snap in snap:
        if match_re and rename_re:
            snap_alias = _alias(match_re, rename_re, _snap)

        if snap_alias:
            snapcraft_fn = build_path / f'{_snap}.yaml'
            _set_snap_alias(snapcraft_fn, snap_alias)

        for line in sh.bash(
                'build-scripts/docker-build',
                _snap,
                _env=env,
                _cwd='release/snap',
                _iter=True):
            click.echo(line.strip())

@cli.command()
@click.option('--channel', required=True, help='Snap channel(s)/track(s) to promote too')
@click.option('--result-dir', required=True, default='release/snap/build',
              help='Path of resulting snap builds')
def release(channel, result_dir):
    """ Promote to a snapstore channel/track

    Usage:

       tox -e py36 -- python3 snaps.py release --channel 1.10.11/edge --result-dir ./release/snap/build
    """
    # TODO: Verify channel is a ver/chan string
    #   re: [\d+\.]+\/(?:edge|stable|candidate|beta)
    for fname in glob.glob(f'{result_dir}/*.snap'):
        try:
            click.echo(f'Running: snapcraft push {fname} --release {channel}')
            for line in sh.snapcraft.push(fname, release=channel, _iter=True):
                click.echo(line.strip())
        except sh.ErrorReturnCode_2 as e:
            click.echo('Failed to upload to snap store')
            click.echo(e.stdout)
            click.echo(e.stderr)
        except sh.ErrorReturnCode_1 as e:
            click.echo('Failed to upload to snap store')
            click.echo(e.stdout)
            click.echo(e.stderr)
        finally:
            click.echo('Broken with no indication why')
            raise SystemExit()


if __name__ == "__main__":
    cli()
