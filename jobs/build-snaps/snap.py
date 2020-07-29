"""
snap.py - Building snaps from source and promoting them to snapstore

"""
import sys
import click
import sh
import os
import yaml
import semver
import tempfile
import itertools
from sh.contrib import git
from urllib.parse import urlparse
from jinja2 import Template
from pathlib import Path
from pymacaroons import Macaroon
from cilib import lp, idm, snapapi, html
from cilib.git import remote_branches, branch_exists, remote_tags
from cilib.run import cmd_ok, capture

# go compiler version map for k8s version releases
K8S_GO_MAP = {
    "1.19": "go/1.15/beta",
    "1.18": "go/1.13/stable",
    "1.17": "go/1.13/stable",
    "1.16": "go/1.13/stable",
    "1.15": "go/1.12/stable",
    "1.14": "go/1.12/stable",
    "1.13": "go/1.12/stable",
}


def _render(tmpl_file, context):
    """ Renders a jinja template with context
    """
    template = Template(tmpl_file.read_text(), keep_trailing_newline=True)
    return template.render(context)


@click.group()
def cli():
    pass


def _sync_branches(snap_list, starting_ver, force, patches, dry_run):
    """ Syncs the upstream k8s release tags with our snap branches

    Usage:
    python3 snap.py sync-branches --snap-list includes/k8s-snap-list.inc
    """
    click.echo(force)
    supported_releases = []
    upstream_releases = remote_tags("https://github.com/kubernetes/kubernetes")

    for rel in upstream_releases:
        _fmt_rel = rel.lstrip("v")
        try:
            semver.parse(_fmt_rel)
            if semver.compare(_fmt_rel, starting_ver) >= 0:
                supported_releases.append(rel)
        except ValueError as error:
            click.echo(f"Skipping invalid {_fmt_rel}: {error}")
    snaps = yaml.safe_load(Path(snap_list).read_text(encoding="utf8"))
    for snap in snaps:
        git_repo = f"git+ssh://cdkbot@git.launchpad.net/snap-{snap}"
        click.echo(f"Checking: {git_repo}")
        snap_releases = remote_branches(git_repo)
        if set(supported_releases).issubset(set(snap_releases)) and not force:
            click.echo("  synced, skipping")
            continue
        if force:
            snap_releases = supported_releases
        else:
            snap_releases = list(set(supported_releases).difference(set(snap_releases)))
        snap_releases.sort()
        for snap_rel in snap_releases:
            click.echo(f"  creating branch for {snap}-{snap_rel}")
            _create_branch(
                git_repo,
                "master",
                snap_rel,
                dry_run=False,
                force=force,
                patches=patches,
            )


def _sync_snaps(snap_list, version, branch_version, tracks):
    """ Creates the snap recipes that upload to the snap store for latest k8s and stable releases
    """
    snaps = yaml.safe_load(Path(snap_list).read_text(encoding="utf8"))
    for snap in snaps:
        git_repo = f"git+ssh://cdkbot@git.launchpad.net/snap-{snap}"
        tracks_to_publish = [track for track in tracks]
        click.echo(f"Generating recipe for {snap}-{version}")
        _create_snap_recipe(
            snap=snap,
            version=version,
            track=tracks_to_publish,
            owner="k8s-jenkaas-admins",
            tag=branch_version,
            repo=git_repo,
            dry_run=False,
            snap_recipe_email=os.environ.get("K8STEAMCI_USR"),
            snap_recipe_password=os.environ.get("K8STEAMCI_PSW"),
        )


@cli.command()
@click.option("--snap-list", help="Path to supported snaps", required=True)
@click.option("--version", help="Major.Minor to sync", required=True)
@click.option("--branch-version", help="Snap branch version", required=True)
@click.option("--tracks", help="Tracks to release to", required=True, multiple=True)
def sync_snaps(snap_list, version, branch_version, tracks):
    return _sync_snaps(snap_list, version, branch_version, tracks)


@cli.command()
@click.option("--snap-list", help="Path to supported snaps", required=True)
@click.option(
    "--starting-ver",
    help="Oldest k8s release to start from",
    required=True,
    default="1.13.7",
)
@click.option("--force", is_flag=True)
@click.option("--patches", help="Path to patches list", required=False)
@click.option("--dry-run", is_flag=True)
def sync_branches(snap_list, starting_ver, force, patches, dry_run):
    return _sync_branches(snap_list, starting_ver, force, patches, dry_run)


@cli.command()
@click.option(
    "--snap",
    default="kubectl",
    help="Snap name to list remote branches for",
    required=True,
)
def sync_branches_list(snap):
    """ Syncs the downstream snap branches to a yaml file for parsing in jobs
    """
    click.echo(f"Checking: git+ssh://cdkbot@git.launchpad.net/snap-{snap}")
    git_repo = f"git+ssh://cdkbot@git.launchpad.net/snap-{snap}"
    snap_releases = remote_branches(git_repo)
    snap_releases.reverse()
    env = os.environ.copy()
    repo = f"https://{env['CDKBOT_GH_USR']}:{env['CDKBOT_GH_PSW']}@github.com/charmed-kubernetes/jenkins"

    with tempfile.TemporaryDirectory() as tmpdir:
        git.clone(repo, tmpdir)
        git.config("user.email", "cdkbot@gmail.com", _env=env, _cwd=tmpdir)
        git.config("user.name", "cdkbot", _env=env, _cwd=tmpdir)
        git.config("--global", "push.default", "simple", _cwd=tmpdir)

        output = Path(f"{tmpdir}/jobs/includes/k8s-snap-branches-list.inc")
        click.echo(f"Saving to {str(output)}")
        output.write_text(yaml.dump(snap_releases, default_flow_style=False, indent=2))
        cmd_ok(f"git add {str(output)}", cwd=tmpdir)
        ret = cmd_ok(
            ["git", "commit", "-m", "Updating k8s snap branches list"], cwd=tmpdir
        )
        if not ret.ok:
            return
        click.echo(f"Committing to {repo}.")
        ret = cmd_ok(["git", "push", repo, "master"], cwd=tmpdir)
        if not ret.ok:
            raise SystemExit("Failed to commit latest snap branches.")


def _create_branch(repo, from_branch, to_branch, dry_run, force, patches):
    """ Creates a git branch based on the upstream snap repo and a version to branch as. This will also update
    the snapcraft.yaml with the correct version to build the snap from in that particular branch.

    These branches must already exist in https://github.com/kubernetes/kubernetes.

    Usage:

    snap.py branch --repo git+ssh://lp_git_user@git.launchpad.net/snap-kubectl \
      --from-branch master \
      --to-branch 1.13.2
    """
    env = os.environ.copy()

    if branch_exists(repo, to_branch, env) and not force:
        click.echo(f"{to_branch} already exists, skipping...")
        sys.exit(0)

    snap_basename = urlparse(repo)
    snap_basename = Path(snap_basename.path).name
    if snap_basename.endswith(".git"):
        snap_basename = snap_basename.rstrip(".git")
    tmpdir = tempfile.TemporaryDirectory()
    snap_basename = tmpdir.name
    capture(["git", "clone", repo, snap_basename])
    capture(["git", "remote", "prune", "origin"], cwd=snap_basename)
    capture(["git", "config" "user.email", "cdkbot@gmail.com"], cwd=snap_basename)
    capture(["git", "config", "user.name", "cdkbot"], cwd=snap_basename)
    capture(["git", "checkout", "-b", to_branch], cwd=snap_basename)

    snapcraft_fn = Path(snap_basename) / "snapcraft.yaml"
    snapcraft_fn_tpl = Path(snap_basename) / "snapcraft.yaml.in"
    if not snapcraft_fn_tpl.exists():
        click.echo(f"{snapcraft_fn_tpl} not found")
        sys.exit(1)

    # Apply patches
    patches_list = []
    if patches:
        patches_path = Path(patches)
        if patches_path.exists():
            click.echo("Patches found, applying.")
            patches_map = yaml.safe_load(patches_path.read_text(encoding="utf8"))
            # TODO: cleanup
            if "all" in patches_map:
                for patch_fn in patches_map["all"]:
                    patch_fn = Path(patch_fn).absolute()
                    shared_path = str(Path("shared") / patch_fn.parts[-1])
                    sh.cp(str(patch_fn), str(shared_path), _cwd=snap_basename)
                    patches_list.append(shared_path)
                    git.add(shared_path, _cwd=snap_basename)
            if to_branch.lstrip("v") in patches_map:
                for patch_fn in patches_map[to_branch.lstrip("v")]:
                    patch_fn = Path(patch_fn).absolute()
                    shared_path = str(Path("shared") / patch_fn.parts[-1])
                    sh.cp(str(patch_fn), str(shared_path), _cwd=snap_basename)
                    patches_list.append(shared_path)
                    git.add(shared_path, _cwd=snap_basename)

    k8s_major_minor = semver.parse(to_branch.lstrip("v"))
    k8s_major_minor_patch = f"{k8s_major_minor['major']}.{k8s_major_minor['minor']}.{k8s_major_minor['patch']}"
    k8s_major_minor = f"{k8s_major_minor['major']}.{k8s_major_minor['minor']}"

    snapcraft_yml_context = {
        "snap_version": to_branch.lstrip("v"),
        "patches": patches_list,
        "go_version": K8S_GO_MAP.get(k8s_major_minor, "go/1.12/stable"),
    }

    # Starting with 1.19 and beyond, build snaps with a base snap of core18 or
    # whatever the fresh catch of the day is
    if semver.compare(k8s_major_minor_patch, "1.19.0") >= 0:
        snapcraft_yml_context["base"] = "core18"

    snapcraft_yml = snapcraft_fn_tpl.read_text()
    snapcraft_yml = _render(snapcraft_fn_tpl, snapcraft_yml_context)
    snapcraft_fn.write_text(snapcraft_yml)
    if not dry_run:
        cmd_ok("git add .", cwd=snap_basename)
        cmd_ok(f"git commit -m 'Creating branch {to_branch}'", cwd=snap_basename)
        cmd_ok(f"git push --force {repo} {to_branch}", cwd=snap_basename)


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
@click.option("--force", is_flag=True)
@click.option("--patches", help="Path to patches list", required=False)
def branch(repo, from_branch, to_branch, dry_run, force, patches):
    return _create_branch(repo, from_branch, to_branch, dry_run, force, patches)


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

    snap.py create-snap-recipe --snap kubectl --version 1.13 --tag v1.13.2 \
      --track 1.13/edge/hotfix-LP123456 \
      --repo git+ssh://$LPCREDS@git.launchpad.net/snap-kubectl \
      --owner k8s-jenkaas-admins \
      --snap-recipe-email myuser@email.com \
      --snap-recipe-password aabbccddee

    """
    _client = lp.Client(stage="production")
    _client.login()

    if not isinstance(track, list):
        track = [track]

    params = {
        "name": snap,
        "owner": owner,
        "version": version,
        "branch": tag,
        "repo": repo,
        "track": track,
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


def _promote_snaps(snap_list, arch, from_track, to_track, exclude_pre, dry_run):
    """ Promotes snaps from latest revision of version on architecture
    """
    snap_list = Path(snap_list)
    if snap_list.exists():
        snap_list = yaml.safe_load(snap_list.read_text(encoding="utf8"))
    else:
        snap_list = []
    snap_list.append("cdk-addons")
    snaps_to_promote = [
        {snap: snapapi.latest(snap, from_track, _arch, exclude_pre)}
        for snap in snap_list
        for _arch in arch.split(" ")
    ]
    for _snap in snaps_to_promote:
        _snap_name = next(iter(_snap))
        rev, uploaded, arch, version, channels = _snap[_snap_name]
        for track in to_track.split(" "):
            click.echo(f"Promoting ({rev}) {_snap} {version} -> {track}")
            try:
                str(sh.snapcraft.release(_snap_name, rev, track))
            except sh.ErrorReturnCode as error:
                click.echo(f"Problem: {error}")
                sys.exit(1)


@cli.command()
@click.option("--snap-list", help="Path to supported snaps", required=True)
@click.option(
    "--arch",
    help="Architecture to use, amd64, arm64, ppc64le or s390x",
    required=True,
    default="amd64",
)
@click.option("--from-track", required=True, help="Snap track to promote from")
@click.option(
    "--to-track",
    help="Snap track to promote to, format as: `[<track>/]<risk>[/<channel>]`",
    required=True,
)
@click.option(
    "--exclude-pre",
    is_flag=True,
    help="Do not count preleases when determining latest snap to promote",
)
@click.option("--dry-run", is_flag=True)
def promote_snaps(snap_list, arch, from_track, to_track, exclude_pre, dry_run):
    """ Provides a way to promote the latest snaps for a particular version and a particular architecture


    Example:
    > snap.py promote-snaps --snap-list k8s-snap-list.yaml \
                            --arch amd64 \
                            --from-track 1.15/edge \
                            --to-track 1.15/stable \
                            --exclude-pre
    """
    return _promote_snaps(snap_list, arch, from_track, to_track, exclude_pre, dry_run)


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


@cli.command()
@click.option("--snap-list", help="Path to supported snaps", required=True)
@click.option("--snap-versions", help="Path to supported snap versions", required=True)
@click.option(
    "--owner",
    help="Owner who can access builds",
    required=True,
    default="k8s-jenkaas-admins",
)
def build_summaries(snap_list, snap_versions, owner):
    """ Return snap build summaries
    """
    _client = lp.Client(stage="production")
    _client.login()

    snap_list_p = Path(snap_list)
    snap_versions_p = Path(snap_versions)

    snap_iter = yaml.safe_load(snap_list_p.read_text())
    snap_versions_iter = yaml.safe_load(snap_versions_p.read_text())

    snaps_to_process = [
        f"{name}-{ver}"
        for name, ver in list(itertools.product(*[snap_iter, snap_versions_iter]))
    ]

    owner_link = _client.owner(owner)
    summaries = []
    for item in snaps_to_process:
        builds = _client.snaps.getByName(name=item, owner=owner_link).builds[:4]

        for build in builds:
            arch = build.distro_arch_series.architecture_tag
            click.echo(f"Summarizing {item} - {arch}")
            summaries.append(
                {
                    "name": f"{item}-{arch}",
                    "created": build.datecreated.strftime("%Y-%m-%d %H:%M:%S"),
                    "started": build.date_started.strftime("%Y-%m-%d %H:%M:%S")
                    if build.date_started
                    else "n/a",
                    "finished": build.datebuilt.strftime("%Y-%m-%d %H:%M:%S")
                    if build.datebuilt
                    else "n/a",
                    "buildstate": build.buildstate,
                    "build_log_url": build.build_log_url,
                    "store_upload_status": build.store_upload_status,
                    "store_upload_errors": build.store_upload_error_messages,
                    "upload_log_url": build.upload_log_url,
                    "channels": build.snap.store_channels,
                }
            )

    # Generate published snaps from snapstore
    click.echo("Retrieving snapstore revisions and publishing information")
    # Add cdk-addons here since we need to check that snap as well from snapstore
    snap_iter.append("cdk-addons")
    published_snaps = [(snap, snapapi.all_published(snap)) for snap in snap_iter]

    tmpl = html.template("snap_summary.html")
    rendered = tmpl.render({"rows": summaries, "published_snaps": published_snaps})

    summary_html_p = Path("snap_summary.html")
    summary_html_p.write_text(rendered)
    cmd_ok("aws s3 cp snap_summary.html s3://jenkaas/snap_summary.html", shell=True)


if __name__ == "__main__":
    cli()
