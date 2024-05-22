""" sync repo script
"""

import click
import yaml
from pathlib import Path
from requests.exceptions import HTTPError
from cilib.github_api import Repository
from cilib import log, enums, lp
from cilib.enums import SNAP_K8S_TRACK_LIST
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
from cilib.version import ChannelRange
from drypy import dryrun


def channel_range(entity):
    range_def = entity.get("channel-range", {})
    definitions = range_def.get("min"), range_def.get("max")
    assert all(isinstance(_, (str, type(None))) for _ in definitions)
    return ChannelRange(*definitions)


@click.group()
def cli():
    pass


@cli.command()
@click.option("--layer-list", required=True, help="Path to supported layer list")
@click.option("--charm-list", required=True, help="Path to supported charm list")
@click.option(
    "--ancillary-list",
    required=True,
    help="Path to additional repos that need to be rebased.",
)
@click.option("--stable-release", required=False, help="Which release branch to create")
@click.option("--filter-by-tag", required=False, help="only build for tags")
@click.option("--dry-run", is_flag=True)
def cut_stable_release(
    layer_list, charm_list, ancillary_list, stable_release, filter_by_tag, dry_run
):
    """This will create a new branch based on the main branch used for the next release.

    layer_list: YAML spec containing git repos and their upstream/downstream properties
    charm_list: YAML spec containing git repos and their upstream/downstream properties
    stable_release: <maj>.<min> version for which this stable release job is run.
    """
    layer_list = yaml.safe_load(Path(layer_list).read_text(encoding="utf8"))
    charm_list = yaml.safe_load(Path(charm_list).read_text(encoding="utf8"))
    ancillary_list = yaml.safe_load(Path(ancillary_list).read_text(encoding="utf8"))
    filter_by_tag = filter_by_tag.split(",")
    if not stable_release:
        stable_release, _ = SNAP_K8S_TRACK_LIST[-1]
    new_branch = f"release_{stable_release}"

    failed = []
    for layer_map in layer_list + charm_list + ancillary_list:
        for layer_name, params in layer_map.items():
            downstream = params["downstream"]
            if not params.get("needs_stable", True):
                log.info(
                    f"Skipping  :: {layer_name:^40} :: does not require stable branch"
                )
                continue

            tags = params.get("tags", None)
            if tags:
                if not any(match in filter_by_tag for match in tags):
                    continue

            if stable_release not in channel_range(params):
                log.info(
                    f"Skipping  :: {layer_name:^40} :: out of supported channel-range"
                )
                continue

            repo = Repository.with_session(*downstream.split("/"), read_only=dry_run)
            default_branch = params.get("branch") or repo.default_branch

            if new_branch in repo.branches:
                log.info(
                    f"Skipping  :: {layer_name:^40} :: {new_branch} already exists"
                )
                continue

            log.info(
                f"Releasing :: {layer_name:^40} :: from: {default_branch} to:{new_branch}"
            )

            try:
                repo.copy_branch(default_branch, new_branch)
            except HTTPError:
                log.error("Failed to copy branch")
                failed.append(layer_name)
    if failed:
        raise RuntimeError("Couldn't create branch for " + ", ".join(failed))


@cli.command()
@click.option("--layer-list", required=True, help="Path to supported layer list")
@click.option("--charm-list", required=True, help="Path to supported charm list")
@click.option(
    "--ancillary-list",
    required=True,
    help="Path to additional repos that need to be rebased.",
)
@click.option("--filter-by-tag", required=False, help="only build for tags")
@click.option("--dry-run", is_flag=True)
@click.option("--from-name", required=True, help="Name of the original branch")
@click.option("--to-name", required=True, help="Name of the new branch")
def rename_branch(
    layer_list, charm_list, ancillary_list, filter_by_tag, dry_run, from_name, to_name
):
    return _rename_branch(
        layer_list,
        charm_list,
        ancillary_list,
        filter_by_tag,
        dry_run,
        from_name,
        to_name,
    )


def _rename_branch(
    layer_list, charm_list, ancillary_list, filter_by_tag, dry_run, from_name, to_name
):
    layer_list = yaml.safe_load(Path(layer_list).read_text(encoding="utf8"))
    charm_list = yaml.safe_load(Path(charm_list).read_text(encoding="utf8"))
    ancillary_list = yaml.safe_load(Path(ancillary_list).read_text(encoding="utf8"))
    filter_by_tag = filter_by_tag.split(",")
    failed = []
    for layer_map in layer_list + charm_list + ancillary_list:
        for layer_name, params in layer_map.items():
            downstream = params["downstream"]

            tags = params.get("tags", None)
            if tags:
                if not any(match in filter_by_tag for match in tags):
                    continue

            if not params.get("supports_rename", True):
                log.info(
                    f"Skipping  :: {layer_name:^40} :: does not support branch renaming"
                )
                continue

            repo = Repository.with_session(*downstream.split("/"), read_only=dry_run)

            if from_name not in repo.branches:
                log.info(f"Skipping  :: {layer_name:^40} :: {from_name} doesn't exist")
                continue

            if to_name in repo.branches:
                log.info(f"Skipping  :: {layer_name:^40} :: {to_name} already exists")
                continue

            log.info(f"Renaming  :: {layer_name:^40} :: from: {from_name} to:{to_name}")

            try:
                repo.rename_branch(from_name, to_name)
            except HTTPError:
                log.error("Failed to rename branch")
                failed.append(layer_name)
    if failed:
        raise RuntimeError("Couldn't create branch for " + ", ".join(failed))


def _tag_stable_forks(
    layer_list, charm_list, k8s_version, bundle_rev, filter_by_tag, bugfix, dry_run
):
    """Tags stable forks to a certain bundle revision for a k8s version

    layer_list: YAML spec containing git repos and their upstream/downstream properties
    bundle_rev: bundle revision to tag for a particular version of k8s

    git tag (ie. ck-{bundle_rev}), this would mean we tagged current
    stable branches for 1.14 with the latest charmed kubernetes(ck) bundle rev
    of {bundle_rev}
    """
    layer_list = yaml.safe_load(Path(layer_list).read_text(encoding="utf8"))
    charm_list = yaml.safe_load(Path(charm_list).read_text(encoding="utf8"))
    filter_by_tag = filter_by_tag.split(",")
    stable_branch = f"release_{k8s_version}"

    failed = []
    for layer_map in layer_list + charm_list:
        for layer_name, params in layer_map.items():
            tags = params.get("tags", None)
            if tags:
                if not any(match in filter_by_tag for match in tags):
                    continue

            if not params.get("needs_tagging", True):
                log.info(f"Skipping  :: {layer_name:^40} :: does not require tagging")
                continue

            if k8s_version not in channel_range(params):
                log.info(
                    f"Skipping  :: {layer_name:^40} :: out of supported channel-range"
                )
                continue

            downstream = params["downstream"]
            if bugfix:
                tag = f"{k8s_version}+{bundle_rev}"
            else:
                tag = f"ck-{k8s_version}-{bundle_rev}"
            repo = Repository.with_session(*downstream.split("/"), read_only=dry_run)

            if tag in repo.tags:
                log.info(f"Skipping  :: {layer_name:^40} :: {tag} already exists")
                continue

            log.info(f"Tagging   :: {layer_name:^40} :: {downstream} ({tag})")
            try:
                repo.tag_branch(stable_branch, tag)
            except HTTPError:
                log.error(f"Problem tagging {layer_name}, skipping..")
                failed.append(layer_name)
    if failed:
        raise RuntimeError("Couldn't create tag for " + ", ".join(failed))


@cli.command()
@click.option("--layer-list", required=True, help="Path to supported layer list")
@click.option("--charm-list", required=True, help="Path to supported charm list")
@click.option(
    "--k8s-version", required=True, help="Version of k8s this bundle provides"
)
@click.option(
    "--bundle-revision", required=True, help="Bundle revision to tag stable against"
)
@click.option("--filter-by-tag", required=False, help="only build for tags")
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
