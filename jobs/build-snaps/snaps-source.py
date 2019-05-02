"""
snaps-source.py - Building snaps from source and promoting them to snapstore

"""
import sys

sys.path.insert(0, ".")

import click
import sh
import os
import glob
import re
import yaml
import operator
import semver
from urllib.parse import urlparse
from jinja2 import Template
from pathlib import Path
from sdk import lp, idm, git
from pymacaroons import Macaroon


def _render(tmpl_file, context):
    """ Renders a jinja template with context
    """
    template = Template(tmpl_file.read_text(), keep_trailing_newline=True)
    return template.render(context)


@click.group()
def cli():
    pass


def _sync_upstream(snap_list, starting_ver):
    """ Syncs the upstream k8s release tags with our snap branches

    Usage:
    snaps-source.py sync-upstream --snap-list includes/k8s-snap-list.inc
    """
    env = os.environ.copy()
    supported_releases = []
    upstream_releases = git.remote_tags("https://github.com/kubernetes/kubernetes")

    for rel in upstream_releases:
        _fmt_rel = rel[1:]
        try:
            semver.parse(_fmt_rel)
            if semver.compare(_fmt_rel, starting_ver) >= 0:
                supported_releases.append(rel)
        except:
            click.echo(f"Skipping invalid version: {rel}")

    snaps = yaml.safe_load(Path(snap_list).read_text(encoding="utf8"))
    for snap in snaps:
        click.echo(f"Checking: git+ssh://cdkbot@git.launchpad.net/snap-{snap}")
        git_repo = f"git+ssh://cdkbot@git.launchpad.net/snap-{snap}"
        snap_releases = git.remote_branches(git_repo)
        if not set(supported_releases).issubset(set(snap_releases)):
            for snap_rel in supported_releases:
                click.echo(f"Creating branch for {snap}-{snap_rel}")
                _create_branch(git_repo, "master", snap_rel, dry_run=False)
                _fmt_version = semver.parse(snap_rel[1:])
                _fmt_version = f'{_fmt_version["major"]}.{_fmt_version["minor"]}'
                click.echo(f"Generating recipe for {snap}-{_fmt_version}")
                _create_snap_recipe(
                    snap=snap,
                    version=_fmt_version,
                    track=f"{_fmt_version}/edge",
                    owner="k8s-jenkaas-admins",
                    tag=snap_rel,
                    repo=git_repo,
                    dry_run=False,
                    snap_recipe_email=os.environ.get("K8STEAMCI_USR"),
                    snap_recipe_password=os.environ.get("K8STEAMCI_PSW"),
                )


@cli.command()
@click.option("--snap-list", help="Path to supported snaps", required=True)
@click.option(
    "--starting-ver",
    help="Oldest k8s release to start from",
    required=True,
    default="1.15.0-alpha.1",
)
def sync_upstream(snap_list, starting_ver):
    return _sync_upstream(snap_list, starting_ver)


def _create_branch(repo, from_branch, to_branch, dry_run):
    """ Creates a git branch based on the upstream snap repo and a version to branch as. This will also update
    the snapcraft.yaml with the correct version to build the snap from in that particular branch.

    These branches must already exist in https://github.com/kubernetes/kubernetes.

    Usage:

    snaps-source.py branch --repo git+ssh://lp_git_user@git.launchpad.net/snap-kubectl \
      --from-branch master \
      --to-branch 1.13.2
    """
    env = os.environ.copy()

    if git.branch_exists(repo, to_branch, env):
        click.echo(f"{to_branch} already exists, skipping...")
        sys.exit(0)

    snap_basename = urlparse(repo)
    snap_basename = Path(snap_basename.path).name
    if snap_basename.endswith(".git"):
        snap_basename = snap_basename.rstrip(".git")
    sh.rm("-rf", snap_basename)
    sh.git.clone(repo, branch=from_branch, _env=env)
    sh.git.config("user.email", "cdkbot@gmail.com", _cwd=snap_basename)
    sh.git.config("user.name", "cdkbot", _cwd=snap_basename)
    sh.git.checkout("-b", to_branch, _cwd=snap_basename)

    snapcraft_fn = Path(snap_basename) / "snapcraft.yaml"
    snapcraft_fn_tpl = Path(snap_basename) / "snapcraft.yaml.in"
    if not snapcraft_fn_tpl.exists():
        click.echo(f"{snapcraft_fn_tpl} not found")
        sys.exit(1)
    snapcraft_yml = snapcraft_fn_tpl.read_text()
    snapcraft_yml = _render(snapcraft_fn_tpl, {"snap_version": to_branch.lstrip("v")})
    snapcraft_fn.write_text(snapcraft_yml)

    if not dry_run:
        sh.git.add(".", _cwd=snap_basename)
        sh.git.commit("-m", f"Creating branch {to_branch}", _cwd=snap_basename)
        sh.git.push(repo, to_branch, _cwd=snap_basename, _env=env)

@cli.command()
@click.option("--repo", help="Git repository to create a new branch on", required=True)
@click.option(
    "--from-branch",
    help="Current git branch to checkout",
    required=True,
    default="master",
)
@click.option(
    "--to-branch",
    help="Git branch to create, this is typically upstream k8s version",
    required=True,
)
@click.option("--dry-run", is_flag=True)
def branch(repo, from_branch, to_branch, dry_run):
    return _create_branch(repo, from_branch, to_branch, dry_run)


def _create_snap_recipe(
    snap,
    version,
    track,
    owner,
    tag,
    repo,
    dry_run,
    snap_recipe_email,
    snap_recipe_password,
):
    """ Creates an new snap recipe in Launchpad

    snap: Name of snap to create the recipe for (ie, kubectl)
    version: snap version channel apply this too (ie, Current patch is 1.13.3 but we want that to go in 1.13 snap channel)
    track: snap store version/risk/branch to publish to (ie, 1.13/edge/hotfix-LP123456)
    owner: launchpad owner of the snap recipe (ie, k8s-jenkaas-admins)
    tag: launchpad git tag to pull snapcraft instructions from (ie, git.launchpad.net/snap-kubectl)
    repo: launchpad git repo (git+ssh://$LPCREDS@git.launchpad.net/snap-kubectl)

    # Note: this account would need access granted to the snaps it want's to publish from the snapstore dashboard
    snap_recipe_email: snapstore email for being able to publish snap recipe from launchpad to snap store
    snap_recipe_password: snapstore password for account being able to publish snap recipe from launchpad to snap store

    Usage:

    snaps-source.py builder --snap kubectl --version 1.13 --tag v1.13.2 \
      --track 1.13/edge/hotfix-LP123456 \
      --repo git+ssh://$LPCREDS@git.launchpad.net/snap-kubectl \
      --owner k8s-jenkaas-admins \
      --snap-recipe-email myuser@email.com \
      --snap-recipe-password aabbccddee

    """
    _client = lp.Client(stage="production")
    _client.login()

    params = {
        "name": snap,
        "owner": owner,
        "version": version,
        "branch": tag,
        "repo": repo,
        "track": [track],
    }

    click.echo(f"  > creating recipe for {params}")
    if dry_run:
        click.echo("dry-run only, exiting.")
        sys.exit(0)
    snap_recipe = _client.create_or_update_snap_recipe(**params)
    caveat_id = snap_recipe.beginAuthorization()
    cip = idm.CanonicalIdentityProvider(
        email=snap_recipe_email, password=snap_recipe_password
    )
    discharge_macaroon = cip.get_discharge(caveat_id).json()
    discharge_macaroon = Macaroon.deserialize(discharge_macaroon["discharge_macaroon"])
    snap_recipe.completeAuthorization(discharge_macaroon=discharge_macaroon.serialize())
    snap_recipe.requestBuilds(archive=_client.archive(), pocket="Updates")


@cli.command()
@click.option("--snap", required=True, help="Snaps to build")
@click.option("--repo", help="Git repository for snap to build", required=True)
@click.option("--version", required=True, help="Version of k8s to build")
@click.option("--tag", required=True, help="Tag to build from")
@click.option(
    "--track",
    required=True,
    help="Snap track to release to, format as: `[<track>/]<risk>[/<branch>]`",
)
@click.option(
    "--owner",
    required=True,
    default="cdkbot",
    help="LP owner with access to managing the snap builds",
)
@click.option(
    "--snap-recipe-email", required=True, help="Snap store recipe authorized email"
)
@click.option(
    "--snap-recipe-password",
    required=True,
    help="Snap store recipe authorized user password",
)
@click.option(
    "--owner",
    required=True,
    default="cdkbot",
    help="LP owner with access to managing the snap builds",
)
@click.option("--dry-run", is_flag=True)
def create_snap_recipe(
    snap,
    version,
    track,
    owner,
    tag,
    repo,
    dry_run,
    snap_recipe_email,
    snap_recipe_password,
):
    return _create_snap_recipe(
        snap,
        version,
        track,
        owner,
        tag,
        repo,
        dry_run,
        snap_recipe_email,
        snap_recipe_password,
    )


if __name__ == "__main__":
    cli()
