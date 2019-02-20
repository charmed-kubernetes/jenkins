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
from sdk import lp, idm


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

    These branches must already exist in https://github.com/juju-solutions/kubernetes, including any hotfix branches.

    Usage:

    snaps-source.py branch --repo git+ssh://lp_git_user@git.launchpad.net/snap-kubectl \
      --from-branch master \
      --to-branch 1.13.2
    """
    env = os.environ.copy()

    try:
        sh.git('ls-remote', '--exit-code', '--heads', repo, to_branch, _env=env)
        click.echo(f'{to_branch} already exists, exiting.')
        sys.exit(0)
    except sh.ErrorReturnCode as e:
        click.echo(f'{to_branch} does not exist, continuing...')

    snap_basename = urlparse(repo)
    snap_basename = Path(snap_basename.path).name
    if snap_basename.endswith('.git'):
        snap_basename = snap_basename.rstrip('.git')
    sh.rm('-rf', snap_basename)
    sh.git.clone(repo, branch=from_branch, _env=env)
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
        sh.git.push(repo, to_branch, _cwd=snap_basename, _env=env)


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
@click.option('--snap-recipe-email', required=True,
              help='Snap store recipe authorized email')
@click.option('--snap-recipe-password', required=True,
              help='Snap store recipe authorized user password')
@click.option('--owner', required=True, default='cdkbot',
              help='LP owner with access to managing the snap builds')
@click.option('--dry-run', is_flag=True)
def create_snap_recipe(
        snap, version, track, owner, branch, repo,
        dry_run, snap_recipe_email, snap_recipe_password):
    """ Creates an new snap recipe in Launchpad

    snap: Name of snap to create the recipe for (ie, kubectl)
    version: snap version channel apply this too (ie, Current patch is 1.13.3 but we want that to go in 1.13 snap channel)
    track: snap store version/risk/branch to publish to (ie, 1.13/edge/hotfix-LP123456)
    owner: launchpad owner of the snap recipe (ie, k8s-jenkaas-admins)
    branch: launchpad git branch to pull snapcraft instructions from (ie, git.launchpad.net/snap-kubectl)
    repo: launchpad git repo (git+ssh://$LPCREDS@git.launchpad.net/snap-kubectl)

    # Note: this account would need access granted to the snaps it want's to publish from the snapstore dashboard
    snap_recipe_email: snapstore email for being able to publish snap recipe from launchpad to snap store
    snap_recipe_password: snapstore password for account being able to publish snap recipe from launchpad to snap store

    Usage:

    snaps-source.py builder --snap kubectl --version 1.13 --branch 1.13.2 \
      --track 1.13/edge/hotfix-LP123456 \
      --repo git+ssh://$LPCREDS@git.launchpad.net/snap-kubectl \
      --owner k8s-jenkaas-admins \
      --snap-recipe-email myuser@email.com \
      --snap-recipe-password aabbccddee

    """
    _client = lp.Client(stage='production')
    _client.login()

    params = {
        'name': snap,
        'owner': owner,
        'version': version,
        'branch': branch,
        'repo': repo,
        'track': [track]
    }

    if dry_run:
        click.echo("dry-run only:")
        click.echo(f"  > creating builder for {params}")
        sys.exit(0)
    snap_recipe = _client.create_or_update_snap_recipe(**params)
    caveat_id = snap_recipe.beginAuthorization()
    cip = idm.CanonicalIdentityProvider(email=snap_recipe_email,
                                        password=snap_recipe_password)
    discharge_macaroon = cip.get_discharge(caveat_id)
    snap_recipe.completeAuthorization(
        discharge_macaroon=discharge_macaroon.json())
    snap_recipe.requestBuilds(archive=_client.archive(), pocket='Updates')


if __name__ == "__main__":
    cli()
