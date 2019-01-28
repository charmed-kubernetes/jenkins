"""
snaps-source.py - Building snaps from source and promoting them to snapstore

"""

import click
import sh
import os
import glob
import re
import yaml
import operator
import sys
from urllib.parse import urlparse
from jinja2 import Template
from pathlib import Path
from sdk import lp


def _render(tmpl_file, context):
    """ Renders a jinja template with context
    """
    template = Template(tmpl_file.read_text(),
                        keep_trailing_newline=True)
    return template.render(context)


@click.group()
def cli():
    pass

@cli.command()
@click.option('--repo', help='Git repository to create a new branch on', required=True)
@click.option('--from-branch', help='Current git branch to checkout', required=True, default='master')
@click.option('--to-branch', help='Git branch to create, this is typically upstream k8s version', required=True)
@click.option('--dry-run', is_flag=True)
def branch(repo, from_branch, to_branch, dry_run):
    """ Creates a git branch based on the upstream snap repo and a version to branch as. This will also update
    the snapcraft.yaml with the correct version to build the snap from in that particular branch.

    Usage:

    snaps-source.py branch --repo git+ssh://lp_git_user@git.launchpad.net/snap-kubectl \
      --from-branch master \
      --to-branch 1.13.2
    """
    try:
        sh.git('ls-remote', '--exit-code', '--heads', repo, to_branch)
        click.echo(f'{to_branch} already exists, exiting.')
        sys.exit(0)
    except sh.ErrorReturnCode as e:
        click.echo(f'{to_branch} does not exist, continuing...')

    snap_basename = urlparse(repo)
    snap_basename = Path(snap_basename.path).name
    if snap_basename.endswith('.git'):
        snap_basename = snap_basename.rstrip('.git')
    sh.rm('-rf', snap_basename)
    sh.git.clone(repo, branch=from_branch)
    sh.git.config('user.email', 'cdkbot@gmail.com', _cwd=snap_basename)
    sh.git.config('user.name', 'cdkbot', _cwd=snap_basename)
    sh.git.checkout('-b', to_branch, _cwd=snap_basename)

    snapcraft_fn = Path(snap_basename) / 'snapcraft.yaml'
    snapcraft_fn_tpl = Path(snap_basename) / 'snapcraft.yaml.in'
    if not snapcraft_fn_tpl.exists():
        click.echo(f'{snapcraft_fn_tpl} not found')
        sys.exit(1)
    snapcraft_yml = snapcraft_fn_tpl.read_text()
    snapcraft_yml = _render(snapcraft_fn_tpl, {'snap_version': to_branch})
    snapcraft_fn.write_text(snapcraft_yml)

    if not dry_run:
        sh.git.add('.', _cwd=snap_basename)
        sh.git.commit('-m', f'Creating branch {to_branch}', _cwd=snap_basename)
        sh.git.push(repo, to_branch, _cwd=snap_basename)


@cli.command()
@click.option('--snap', required=True, help='Snaps to build')
@click.option('--repo', help='Git repository for snap to build', required=True)
@click.option('--version', required=True, help='Version of k8s to build')
@click.option('--branch', required=True, help='Branch to build from')
@click.option(
    '--track', required=True,
    help='Snap track to release to, format as: `[<track>/]<risk>[/<branch>]`')
@click.option('--owner', required=True, default='cdkbot',
              help='LP owner with access to managing the snap builds')
@click.option('--dry-run', is_flag=True)
def builder(snap, version, track, owner, branch, repo, dry_run):
    """ Creates an new LP builder for snaps

    Usage:

    snaps.py builder --snap kubectl --version 1.13 --branch 1.13.2 \
      --track 1.13/edge/hotfix-LP123456 \
      --repo git+ssh://$LPCREDS@git.launchpad.net/snap-kubectl
    """
    _client = lp.Client(stage='production')
    _client.login()

    params = {
        'name': snap,
        'owner': owner,
        'version': version,
        'branch': branch,
        'repo': repo,
        'track': track
    }

    if dry_run:
        click.echo("dry-run only:")
        click.echo(f"  > creating builder for {params}")
        sys.exit(0)
    _client.create_or_update_snap_builder(**params)


if __name__ == "__main__":
    cli()
