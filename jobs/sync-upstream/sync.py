""" sync repo script
"""
import click
import sh
import os
import uuid
import yaml
from pathlib import Path
from sh.contrib import git
from cilib import log, enums, lp
from cilib.git import default_gh_branch
from cilib.models.repos.kubernetes import (
    UpstreamKubernetesRepoModel,
    InternalKubernetesRepoModel,
    CriToolsUpstreamRepoModel,
    InternalCriToolsRepoModel,
    CNIPluginsUpstreamRepoModel,
    InternalCNIPluginsRepoModel,
)
from cilib.models.repos.snaps import (
    SnapKubeApiServerRepoModel,
    SnapKubeControllerManagerRepoModel,
    SnapKubeProxyRepoModel,
    SnapKubeSchedulerRepoModel,
    SnapKubectlRepoModel,
    SnapKubeadmRepoModel,
    SnapKubeletRepoModel,
    SnapKubernetesTestRepoModel,
    SnapCdkAddonsRepoModel,
)
from cilib.models.repos.debs import (
    DebCriToolsRepoModel,
    DebKubeadmRepoModel,
    DebKubectlRepoModel,
    DebKubeletRepoModel,
    DebKubernetesCniRepoModel,
)
from cilib.models.repos.charms import CharmRepoModel
from cilib.service.snap import SnapService
from cilib.service.deb import DebService, DebCNIService, DebCriToolsService
from cilib.service.ppa import PPAService
from cilib.service.charm import CharmService
from drypy import dryrun


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
    """This will merge each layers master onto the stable branches.

    PLEASE NOTE: This step should come after each stable branch has been tagged
    and references a current stable bundle revision.

    layer_list: YAML spec containing git repos and their upstream/downstream properties
    charm_list: YAML spec containing git repos and their upstream/downstream properties
    """
    layer_list = yaml.safe_load(Path(layer_list).read_text(encoding="utf8"))
    charm_list = yaml.safe_load(Path(charm_list).read_text(encoding="utf8"))
    ancillary_list = yaml.safe_load(Path(ancillary_list).read_text(encoding="utf8"))
    new_env = os.environ.copy()

    failed_to_release = []
    for layer_map in layer_list + charm_list + ancillary_list:
        for layer_name, repos in layer_map.items():
            downstream = repos["downstream"]
            if not repos.get("needs_stable", True):
                continue

            tags = repos.get("tags", None)
            if tags:
                if not any(match in filter_by_tag for match in tags):
                    continue

            auth = (new_env.get("CDKBOT_GH_USR"), new_env.get("CDKBOT_GH_PSW"))
            default_branch = repos.get("branch") or default_gh_branch(
                downstream, auth=auth
            )

            log.info(
                f"Releasing :: {layer_name:^35} :: from: {default_branch} to: stable"
            )
            downstream = f"https://{':'.join(auth)}@github.com/{downstream}"
            identifier = str(uuid.uuid4())
            os.makedirs(identifier)
            for line in git.clone(downstream, identifier, _iter=True):
                log.info(line)
            git_rev_default = (
                git("rev-parse", f"origin/{default_branch}", _cwd=identifier)
                .stdout.decode()
                .strip()
            )
            git_rev_stable = (
                git("rev-parse", "origin/stable", _cwd=identifier)
                .stdout.decode()
                .strip()
            )
            if git_rev_default == git_rev_stable:
                log.info(f"Skipping  :: {layer_name:^35} :: {default_branch} == stable")
                continue
            log.info(f"Commits   :: {layer_name:^35} :: {default_branch} != stable")
            log.info(f"  {default_branch:10}= {git_rev_default:32}")
            log.info(f"  {'stable':10}= {git_rev_stable:32}")
            for line in git(
                "rev-list", f"origin/stable..origin/{default_branch}", _cwd=identifier
            ):
                for line in git.show(
                    "--format=%h %an '%s' %cr",
                    "--no-patch",
                    line.strip(),
                    _cwd=identifier,
                ):
                    log.info("    " + line.strip())
            if not dry_run:
                git.config("user.email", "cdkbot@juju.solutions", _cwd=identifier)
                git.config("user.name", "cdkbot", _cwd=identifier)
                git.config("--global", "push.default", "simple")
                git.checkout("-f", "stable", _cwd=identifier)
                git.reset(default_branch, _cwd=identifier)
                for line in git.push(
                    "origin", "stable", "-f", _cwd=identifier, _iter=True
                ):
                    log.info(line)


def _tag_stable_forks(
    layer_list, charm_list, k8s_version, bundle_rev, filter_by_tag, bugfix, dry_run
):
    """Tags stable forks to a certain bundle revision for a k8s version

    layer_list: YAML spec containing git repos and their upstream/downstream properties
    bundle_rev: bundle revision to tag for a particular version of k8s

    git tag (ie. ck-{bundle_rev}), this would mean we tagged current
    stable branches for 1.14 with the latest charmed kubernetes(ck) bundle rev
    of {bundle_rev}

    TODO: Switch to different merge strategy
    git checkout master
    git checkout -b staging
    git merge stable -s ours
    git checkout stable
    git reset staging
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
                log.info(f"Skipping {layer_name} :: does not require tagging")
                continue

            log.info(f"Tagging {layer_name} ({tag}) :: {repos['downstream']}")
            if not dry_run:
                downstream = f"https://{new_env['CDKBOT_GH_USR']}:{new_env['CDKBOT_GH_PSW']}@github.com/{downstream}"
                identifier = str(uuid.uuid4())
                os.makedirs(identifier)
                for line in git.clone(downstream, identifier, _iter=True):
                    log.info(line)
                git.config("user.email", "cdkbot@juju.solutions", _cwd=identifier)
                git.config("user.name", "cdkbot", _cwd=identifier)
                git.config("--global", "push.default", "simple")
                git.checkout("stable", _cwd=identifier)
                try:
                    for line in git.tag(
                        "--force", tag, _cwd=identifier, _iter=True, _bg_exc=False
                    ):
                        log.info(line)
                    for line in git.push(
                        "--force",
                        "origin",
                        tag,
                        _cwd=identifier,
                        _bg_exc=False,
                        _iter=True,
                    ):
                        log.info(line)
                except sh.ErrorReturnCode as error:
                    log.info(
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


@cli.command()
@click.option("--dry-run", is_flag=True)
def ppas(dry_run):
    """Sync ppas"""
    dryrun(dry_run)
    client = lp.Client()
    client.login()
    ppa_service_obj = PPAService(client.owner("k8s-maintainers"))
    ppa_service_obj.sync()


@cli.command()
@click.option("--sign-key", help="GPG Sign key ID", required=True)
@click.option("--dry-run", is_flag=True)
@click.option("--force", is_flag=True)
def debs(sign_key, dry_run, force):
    """Syncs debs"""
    dryrun(dry_run)

    client = lp.Client()
    client.login()
    ppas = client.ppas("k8s-maintainers")

    debs_to_process = [
        DebKubeadmRepoModel(),
        DebKubectlRepoModel(),
        DebKubeletRepoModel(),
    ]
    kubernetes_repo = InternalKubernetesRepoModel()

    # Sync all deb branches
    for _deb in debs_to_process:
        deb_service_obj = DebService(_deb, kubernetes_repo, ppas, sign_key)
        deb_service_obj.sync_from_upstream()
        deb_service_obj.sync_debs(force)

    cri_tools = DebCriToolsRepoModel()
    cri_tools_service_obj = DebCriToolsService(
        cri_tools, InternalCriToolsRepoModel(), ppas, sign_key
    )
    cri_tools_service_obj.sync_from_upstream()
    cri_tools_service_obj.sync_debs(force)

    kubernetes_cni = DebKubernetesCniRepoModel()
    kubernetes_cni_service_obj = DebCNIService(
        kubernetes_cni, InternalCNIPluginsRepoModel(), ppas, sign_key
    )
    kubernetes_cni_service_obj.sync_from_upstream()
    kubernetes_cni_service_obj.sync_debs(force)


@cli.command()
@click.option("--dry-run", is_flag=True)
def sync_internal_tags(dry_run):
    """Syncs upstream to downstream internal k8s tags"""
    dryrun(dry_run)
    # List of tuples containing upstream, downstream models and a starting semver
    repos_map = [
        (
            UpstreamKubernetesRepoModel(),
            InternalKubernetesRepoModel(),
            enums.K8S_STARTING_SEMVER,
        ),
        (
            CriToolsUpstreamRepoModel(),
            InternalCriToolsRepoModel(),
            enums.K8S_CRI_TOOLS_SEMVER,
        ),
        (
            CNIPluginsUpstreamRepoModel(),
            InternalCNIPluginsRepoModel(),
            enums.K8S_CNI_SEMVER,
        ),
    ]

    for repo in repos_map:
        upstream, downstream, starting_semver = repo
        tags_to_sync = upstream.tags_subset_semver_point(downstream, starting_semver)
        if not tags_to_sync:
            click.echo(f"All synced up: {upstream} == {downstream}")
            continue
        upstream.clone()
        upstream.remote_add("downstream", downstream.repo, cwd=upstream.name)
        for tag in tags_to_sync:
            click.echo(f"Syncing repo {upstream} => {downstream}, tag => {tag}")
            upstream.push("downstream", tag, cwd=upstream.name)


@cli.command()
@click.option("--dry-run", is_flag=True)
def forks(dry_run):
    """Syncs all upstream forks"""
    # Try auto-merge; if conflict: update_readme.py && git add README.md && git
    # commit. If that fails, too, then it was a JSON conflict that will have to
    # be handled manually.
    dryrun(dry_run)
    repos_to_process = [
        CharmService(repo)
        for repo in CharmRepoModel.load_repos(enums.CHARM_LAYERS_MAP + enums.CHARM_MAP)
    ]
    for repo in repos_to_process:
        repo.sync()


@cli.command()
@click.option("--dry-run", is_flag=True)
def snaps(dry_run):
    """Syncs the snap branches, keeps snap builds in sync, and makes sure the latest snaps are published into snap store"""
    dryrun(dry_run)
    snaps_to_process = [
        SnapKubeApiServerRepoModel(),
        SnapKubeControllerManagerRepoModel(),
        SnapKubeProxyRepoModel(),
        SnapKubeSchedulerRepoModel(),
        SnapKubectlRepoModel(),
        SnapKubeadmRepoModel(),
        SnapKubeletRepoModel(),
        SnapKubernetesTestRepoModel(),
    ]

    kubernetes_repo = InternalKubernetesRepoModel()

    # Sync all snap branches
    for _snap in snaps_to_process:
        snap_service_obj = SnapService(_snap, kubernetes_repo)
        snap_service_obj.sync_from_upstream()
        snap_service_obj.sync_all_track_snaps()
        snap_service_obj.sync_stable_track_snaps()

    # Handle cdk-addons sync separetely
    cdk_addons = SnapCdkAddonsRepoModel()
    cdk_addons_service_obj = SnapService(cdk_addons, kubernetes_repo)
    cdk_addons_service_obj.sync_stable_track_snaps()


@cli.command()
@click.option("--branch", required=True, help="Branch to build from")
@click.option("--dry-run", is_flag=True)
def snap_from_branch(branch, dry_run):
    """Syncs the snap branches, keeps snap builds in sync, and makes sure the latest snaps are published into snap store"""
    dryrun(dry_run)
    snaps_to_process = [
        SnapKubeApiServerRepoModel(),
        SnapKubeControllerManagerRepoModel(),
        SnapKubeProxyRepoModel(),
        SnapKubeSchedulerRepoModel(),
        SnapKubectlRepoModel(),
        SnapKubeadmRepoModel(),
        SnapKubeletRepoModel(),
        SnapKubernetesTestRepoModel(),
    ]

    kubernetes_repo = InternalKubernetesRepoModel()

    # Sync all snap branches
    for _snap in snaps_to_process:
        snap_service_obj = SnapService(_snap, kubernetes_repo)
        snap_service_obj.build_snap_from_branch(branch)


if __name__ == "__main__":
    cli()
