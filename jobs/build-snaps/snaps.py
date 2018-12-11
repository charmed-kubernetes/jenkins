"""
snaps.py - Interface for building and publishing snaps

"""

import click
import sh
import os
import glob
import re
from pathlib import Path

@click.group()
def cli():
    pass

@cli.command()
@click.option('--snap', required=True, multiple=True, help='Snaps to build')
@click.option('--version', required=True, help='Version of k8s to build')
@click.option('--arch', required=True, default='amd64', help='Architecture to build against')
def build(snap, version, arch):
    """ Build snaps

    Usage:

    snaps.py build --snap kubectl --snap kube-proxy --version 1.10.3 --arch amd64
    """
    if not version.startswith('v'):
        version = f'v{version}'
    env = os.environ.copy()
    env['KUBE_VERSION'] = version
    env['KUBE_ARCH'] = arch
    sh.git.clone('https://github.com/juju-solutions/release.git',
                 branch='rye/snaps', depth='1')
    for _snap in snap:
        for line in sh.bash(
                'build-scripts/docker-build',
                _snap,
                _env=env,
                _cwd='release/snap',
                _iter=True):
            click.echo(line.strip())

@cli.command()
@click.option('--match-re', help='Regex pattern to match files')
@click.option('--rename-re', help='Regex pattern to rename snap files to')
@click.option('--result-dir', required=True, default='release/snap/build',
              help='Path of resulting snap builds')
def process(match_re, rename_re, result_dir):
    """ Provide any filename substitutions for things like kubectl-eks...snap

    Usage:

      tox -e py36 -- python3 snaps.py process --match-re \'(?=\\S*[-]*)([a-zA-Z-]+)(.*)\' --rename-re \'\\1-eks_\\2\'"
    """
    if match_re and rename_re:
        for filename in glob.glob(f'{result_dir}/*.snap'):
            filepath = Path(filename)
            filename = filepath.parts[-1]
            click.echo(f'Querying {filename}')
            new_name = re.sub(match_re, fr'{rename_re}', filename)
            click.echo(f'Match regex: {match_re}, '
                       f'Rename regex: {rename_re}, '
                       f'Output name: {new_name}')
            sh.sudo.mv(filepath, filepath.parent / new_name)


if __name__ == "__main__":
    cli()
