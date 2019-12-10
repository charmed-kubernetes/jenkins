""" sync repo script
"""
import sys
import click
import sh
import os
import uuid
import yaml
from pathlib import Path
from urllib.parse import urlparse
from sh.contrib import git


@click.group()
def cli():
    pass


@cli.command()
@click.option("--layer-list", required=True, help="Path to supported layer list")
@click.option("--charm-list", required=True, help="Path to supported charm list")
@click.option(
    "--ancillary-list",
    required=True,
    help="Path to additionall repos that need to be rebased.",
)
@click.option(
    "--filter-by-tag", required=False, help="only build for tags", multiple=True
)
@click.option("--dry-run", is_flag=True)
def cut_stable_release(layer_list, charm_list, ancillary_list, filter_by_tag, dry_run):
    return _cut_stable_release(
        layer_list, charm_list, ancillary_list, filter_by_tag, dry_run
    )


def _cut_stable_release(layer_list, charm_list, ancillary_list, filter_by_tag, dry_run):
    """ This will force push each layers master onto the stable branches.

    PLEASE NOTE: This step should come after each stable branch has been tagged
    and references a current stable bundle revision.

    layer_list: YAML spec containing git repos and their upstream/downstream properties
    charm_list: YAML spec containing git repos and their upstream/downstream properties
    """
    layer_list = yaml.safe_load(Path(layer_list).read_text(encoding="utf8"))
    charm_list = yaml.safe_load(Path(charm_list).read_text(encoding="utf8"))
    ancillary_list = yaml.safe_load(Path(ancillary_list).read_text(encoding="utf8"))
    new_env = os.environ.copy()
    for layer_map in layer_list + charm_list + ancillary_list:
        for layer_name, repos in layer_map.items():
            downstream = repos["downstream"]
            if not repos.get("needs_stable", True):
                continue

            tags = repos.get("tags", None)
            if tags:
                if not any(match in filter_by_tag for match in tags):
                    continue

            click.echo(f"Releasing :: {layer_name:^35} :: from: master to: stable")
            if not dry_run:
                downstream = f"https://{new_env['CDKBOT_GH_USR']}:{new_env['CDKBOT_GH_PSW']}@github.com/{downstream}"
                identifier = str(uuid.uuid4())
                os.makedirs(identifier)
                for line in git.clone(downstream, identifier, _iter=True):
                    click.echo(line)
                git_rev_master = git(
                    "rev-parse", "origin/master", _cwd=identifier
                ).stdout.decode()
                git_rev_stable = git(
                    "rev-parse", "origin/stable", _cwd=identifier
                ).stdout.decode()
                if git_rev_master == git_rev_stable:
                    click.echo(f"Skipping  :: {layer_name:^35} :: master == stable")
                    continue
                git.config("user.email", "cdkbot@juju.solutions", _cwd=identifier)
                git.config("user.name", "cdkbot", _cwd=identifier)
                git.config("--global", "push.default", "simple")
                git.branch("-f", "stable", "master", _cwd=identifier)
                for line in git.push(
                    "-f", "origin", "stable", _cwd=identifier, _iter=True
                ):
                    click.echo(line)


def _tag_stable_forks(
    layer_list, charm_list, k8s_version, bundle_rev, filter_by_tag, bugfix, dry_run
):
    """ Tags stable forks to a certain bundle revision for a k8s version

    layer_list: YAML spec containing git repos and their upstream/downstream properties
    bundle_rev: bundle revision to tag for a particular version of k8s

    git tag (ie. ck-{bundle_rev}), this would mean we tagged current
    stable branches for 1.14 with the latest charmed kubernetes(ck) bundle rev
    of {bundle_rev}
    """
    layer_list = yaml.safe_load(Path(layer_list).read_text(encoding="utf8"))
    charm_list = yaml.safe_load(Path(charm_list).read_text(encoding="utf8"))
    new_env = os.environ.copy()
    for layer_map in layer_list + charm_list:
        for layer_name, repos in layer_map.items():

            tags = repos.get("tags", None)
            if tags:
                if not any(match in filter_by_tag for match in tags):
                    continue

            downstream = repos["downstream"]
            if bugfix:
                tag = f"{k8s_version}+{bundle_rev}"
            else:
                tag = f"ck-{k8s_version}-{bundle_rev}"
            if not repos.get("needs_tagging", True):
                click.echo(f"Skipping {layer_name} :: does not require tagging")
                continue

            click.echo(f"Tagging {layer_name} ({tag}) :: {repos['downstream']}")
            if not dry_run:
                downstream = f"https://{new_env['CDKBOT_GH_USR']}:{new_env['CDKBOT_GH_PSW']}@github.com/{downstream}"
                identifier = str(uuid.uuid4())
                os.makedirs(identifier)
                for line in git.clone(downstream, identifier, _iter=True):
                    click.echo(line)
                git.config("user.email", "cdkbot@juju.solutions", _cwd=identifier)
                git.config("user.name", "cdkbot", _cwd=identifier)
                git.config("--global", "push.default", "simple")
                git.checkout("stable", _cwd=identifier)
                try:
                    for line in git.tag(
                        "--force", tag, _cwd=identifier, _iter=True, _bg_exc=False
                    ):
                        click.echo(line)
                    for line in git.push(
                        "--force", "origin", tag, _cwd=identifier, _bg_exc=False, _iter=True
                    ):
                        click.echo(line)
                except sh.ErrorReturnCode as error:
                    click.echo(
                        f"Problem tagging: {error.stderr.decode().strip()}, will skip for now.."
                    )


@cli.command()
@click.option("--layer-list", required=True, help="Path to supported layer list")
@click.option("--charm-list", required=True, help="Path to supported charm list")
@click.option(
    "--k8s-version", required=True, help="Version of k8s this bundle provides"
)
@click.option(
    "--bundle-revision", required=True, help="Bundle revision to tag stable against"
)
@click.option(
    "--filter-by-tag", required=False, help="only build for tags", multiple=True
)
@click.option("--bugfix", is_flag=True)
@click.option("--dry-run", is_flag=True)
def tag_stable(
    layer_list, charm_list, k8s_version, bundle_revision, filter_by_tag, bugfix, dry_run
):
    return _tag_stable_forks(
        layer_list,
        charm_list,
        k8s_version,
        bundle_revision,
        filter_by_tag,
        bugfix,
        dry_run,
    )


def _sync_upstream(layer_list, dry_run):
    """ Syncs any of the forked upstream repos

    layer_list: YAML spec containing git repos and their upstream/downstream properties
    """
    layer_list = yaml.safe_load(Path(layer_list).read_text(encoding="utf8"))
    new_env = os.environ.copy()

    for layer_map in layer_list:
        for layer_name, repos in layer_map.items():
            upstream = repos["upstream"]
            downstream = repos["downstream"]
            if urlparse(upstream).path.lstrip("/") == downstream:
                click.echo(f"Skipping {layer_name} :: {upstream} == {downstream}")
                continue
            click.echo(
                f"Syncing {layer_name} :: {repos['upstream']} -> {repos['downstream']}"
            )
            if not dry_run:
                downstream = f"https://{new_env['CDKBOT_GH_USR']}:{new_env['CDKBOT_GH_PSW']}@github.com/{downstream}"
                identifier = str(uuid.uuid4())
                os.makedirs(identifier)
                try:
                    for line in git.clone(
                        downstream, identifier, _iter=True, _bg_exc=False
                    ):
                        click.echo(line)
                except sh.ErrorReturnCode as e:
                    click.echo(f"Failed to clone repo: {e.stderr.decode()}")
                    sys.exit(1)
                git.config("user.email", "cdkbot@juju.solutions", _cwd=identifier)
                git.config("user.name", "cdkbot", _cwd=identifier)
                git.config("--global", "push.default", "simple")
                git.remote("add", "upstream", upstream, _cwd=identifier)
                for line in git.fetch(
                    "upstream", _cwd=identifier, _iter=True, _bg_exc=False
                ):
                    click.echo(line)
                git.checkout("master", _cwd=identifier)
                # if "layer-index" in downstream:
                #     sh.python3("update_readme.py", _cwd=identifier)
                for line in git.merge(
                    "upstream/master", _cwd=identifier, _iter=True, _bg_exc=False
                ):
                    click.echo(line)
                for line in git.push(
                    "origin", _cwd=identifier, _iter=True, _bg_exc=True
                ):
                    click.echo(line)


@cli.command()
@click.option("--layer-list", required=True, help="Path to supported layer list")
@click.option("--dry-run", is_flag=True)
def forks(layer_list, dry_run):
    """ Syncs all upstream forks
    """
    # Try auto-merge; if conflict: update_readme.py && git add README.md && git
    # commit. If that fails, too, then it was a JSON conflict that will have to
    # be handled manually.
    return _sync_upstream(layer_list, dry_run)


if __name__ == "__main__":
    cli()
