import click
import traceback
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from time import sleep
from sh.contrib import git

from builder_local import BundleBuildEntity, BuildEnv, BuildEntity, BuildType
from builder_launchpad import LPBuildEntity
from cilib.version import RISKS

LAUNCHPAD_SUBMIT_WORKERS = 4
LAUNCHPAD_POLL_SECONDS = 30


def _prepare_build(entity, force, to_channels):
    entity.echo("Starting")
    if not entity.within_channel_bounds(to_channels=to_channels):
        entity.echo("Skipped due to channel boundaries")
        return False
    entity.setup()
    entity.echo(f"Details: {entity}")
    if force:
        entity.echo("Build forced.")
        return True
    return entity.charm_changes


def _publish_build(entity, to_channels):
    entity.resource_build()
    for artifact in entity.artifacts:
        entity.push(artifact)
        entity.assemble_resources(artifact, to_channels=to_channels)
        entity.release(artifact, to_channels=to_channels)


def _submit_launchpad_build(entity, force, to_channels):
    if not _prepare_build(entity, force, to_channels):
        return False
    entity.submit_build()
    return True


def _collect_launchpad_builds(submissions, to_channels, failures):
    pending = []
    while submissions or pending:
        if submissions:
            # A slow source sync must not stop us collecting other recipes.
            done, _ = wait(
                submissions,
                timeout=LAUNCHPAD_POLL_SECONDS if pending else None,
                return_when=FIRST_COMPLETED,
            )
            for future in done:
                entity = submissions.pop(future)
                try:
                    if future.result():
                        pending.append(entity)
                        continue
                except Exception:
                    entity.echo(traceback.format_exc())
                    failures.append(entity)
                entity.echo("Stopping")
        else:
            sleep(LAUNCHPAD_POLL_SECONDS)

        still_pending = []
        for entity in pending:
            try:
                if not entity.collect_build():
                    still_pending.append(entity)
                    continue
                _publish_build(entity, to_channels)
            except Exception:
                entity.echo(traceback.format_exc())
                failures.append(entity)
            entity.echo("Stopping")
        pending = still_pending


@click.group()
def cli():
    """Define click group."""


@cli.command()
@click.option(
    "--charm-list", required=True, help="path to a file with list of charms in YAML"
)
@click.option("--layer-list", required=True, help="list of layers in YAML format")
@click.option("--layer-index", required=True, help="Charm layer index")
@click.option(
    "--charm-branch",
    required=True,
    help="Git branch to build charm from",
    default="",
)
@click.option(
    "--layer-branch",
    required=True,
    help="Git branch to pull layers/interfaces from",
    default="main",
)
@click.option(
    "--resource-spec", required=True, help="YAML Spec of resource keys and filenames"
)
@click.option(
    "--filter-by-tag",
    required=True,
    help="only build for charms matching a tag, comma separate list",
)
@click.option(
    "--track", required=True, help="track to promote charm to", default="latest"
)
@click.option(
    "--to-channel", required=True, help="channel to promote charm to", default="edge"
)
@click.option("--force", is_flag=True)
def build(
    charm_list,
    layer_list,
    layer_index,
    charm_branch,
    layer_branch,
    resource_spec,
    filter_by_tag,
    track,
    to_channel,
    force,
):
    """Build a set of charms and publish with their resources."""
    # sh.which.charm(_tee=True, _out=lambda m: click.echo(f"charm -> {m}"))
    # sh.which.charmcraft(_tee=True, _out=lambda m: click.echo(f"charmcraft -> {m}"))
    # sh.snap.list(_tee=True, _out=lambda m: click.echo(f"snap list -> {m}"))

    build_env = BuildEnv(build_type=BuildType.CHARM)
    build_env.db["build_args"] = {
        "job_list": charm_list,
        "layer_list": layer_list,
        "layer_index": layer_index,
        "branch": charm_branch,
        "layer_branch": layer_branch,
        "resource_spec": resource_spec,
        "filter_by_tag": filter_by_tag.split(","),
        "track": track,
        "to_channel": to_channel,
        "force": force,
    }
    build_env.clean()
    build_env.pull_layers()

    entities = []
    for charm_map in build_env.job_list:
        for charm_name, charm_opts in charm_map.items():
            if any(tag in build_env.filter_by_tag for tag in charm_opts["tags"]):
                cls = (
                    LPBuildEntity
                    if charm_opts.get("builder") == "launchpad"
                    else BuildEntity
                )
                charm_entity = cls(build_env, charm_name, charm_opts)
                entities.append(charm_entity)
                build_env.echo(f"Queued {charm_entity.entity} for building")

    failed_entities = []
    to_channels = [
        f"{build_env.track}/{chan.lower()}" if (chan.lower() in RISKS) else chan
        for chan in build_env.to_channels
    ]

    with ThreadPoolExecutor(max_workers=LAUNCHPAD_SUBMIT_WORKERS) as executor:
        submissions = {}
        local_entities = []
        for entity in entities:
            if isinstance(entity, LPBuildEntity):
                future = executor.submit(
                    _submit_launchpad_build, entity, build_env.force, to_channels
                )
                submissions[future] = entity
            else:
                local_entities.append(entity)

        # Local builds and uploads share this Jenkins worker; keep them serial.
        for entity in local_entities:
            try:
                if _prepare_build(entity, build_env.force, to_channels):
                    entity.charm_build()
                    _publish_build(entity, to_channels)
            except Exception:
                entity.echo(traceback.format_exc())
                failed_entities.append(entity)
            finally:
                entity.echo("Stopping")

        _collect_launchpad_builds(submissions, to_channels, failed_entities)

    if any(failed_entities):
        count = len(failed_entities)
        plural = "s" if count > 1 else ""
        raise SystemExit(
            f"Encountered {count} Charm Build Failure{plural}:\n\t"
            + ", ".join(ch.name for ch in failed_entities)
        )

    build_env.save()


@cli.command()
@click.option("--bundle-list", required=True, help="list of bundles in YAML format")
@click.option(
    "--bundle-branch",
    default="main",
    required=True,
    help="Upstream branch to build bundles from",
)
@click.option(
    "--filter-by-tag",
    required=True,
    help="only build for charms matching a tag, comma separate list",
)
@click.option(
    "--bundle-repo",
    required=True,
    help="upstream repo for bundle builder",
    default="https://github.com/charmed-kubernetes/bundle.git",
)
@click.option(
    "--track", required=True, help="track to promote charm to", default="latest"
)
@click.option(
    "--to-channel", required=True, help="channels to promote bundle to", default="edge"
)
@click.option("--force", is_flag=True)
def build_bundles(
    bundle_list, bundle_branch, filter_by_tag, bundle_repo, track, to_channel, force
):
    """Build list of bundles from a specific branch according to filters."""
    build_env = BuildEnv(build_type=BuildType.BUNDLE)
    build_env.db["build_args"] = {
        "job_list": bundle_list,
        "branch": bundle_branch,
        "filter_by_tag": filter_by_tag.split(","),
        "track": track,
        "to_channel": to_channel,
        "force": force,
    }

    build_env.clean()
    default_repo_dir = build_env.default_repo_dir
    git("clone", bundle_repo, default_repo_dir, branch=bundle_branch)

    entities = []
    for bundle_map in build_env.job_list:
        for bundle_name, bundle_opts in bundle_map.items():
            if any(tag in build_env.filter_by_tag for tag in bundle_opts["tags"]):
                if "downstream" in bundle_opts:
                    bundle_opts["sub-repo"] = bundle_name
                    bundle_opts["src_path"] = build_env.repos_dir / bundle_name
                else:
                    bundle_opts["src_path"] = build_env.default_repo_dir
                bundle_opts["dst_path"] = build_env.bundles_dir / bundle_name

                build_entity = BundleBuildEntity(build_env, bundle_name, bundle_opts)
                entities.append(build_entity)

    to_channels = [
        f"{build_env.track}/{chan.lower()}" if (chan.lower() in RISKS) else chan
        for chan in build_env.to_channels
    ]

    for entity in entities:
        entity.echo("Starting")
        try:
            if "downstream" in entity.opts:
                # clone bundle repo override
                entity.setup()

            entity.echo(f"Details: {entity}")
            for channel in to_channels:
                entity.bundle_build(channel)

                # Bundles are built easily, but it's pointless to push the bundle
                # if the crcs of each file in the bundle zips are the same
                for artifact in entity.artifacts:
                    if build_env.force or entity.bundle_differs(artifact):
                        entity.echo(
                            f"Pushing built bundle for channel={channel} (forced={build_env.force})."
                        )
                        entity.push(artifact)
                        entity.release(artifact, to_channels=[channel])
                entity.reset_artifacts()
        finally:
            entity.echo("Stopping")

    build_env.save()


@cli.command()
@click.option("--charm-list", required=True, help="path to charm list YAML")
@click.option(
    "--filter-by-tag",
    required=True,
    help="only build for charms matching a tag, comma separate list",
)
@click.option(
    "--track", required=True, help="track to promote charm to", default="latest"
)
@click.option(
    "--from-channel",
    default="unpublished",
    required=True,
    help="Charm channel to publish from",
)
@click.option("--to-channel", required=True, help="Charm channel to publish to")
@click.option("--dry-run", is_flag=True)
def promote(charm_list, filter_by_tag, track, from_channel, to_channel, dry_run):
    """
    Promote channel for a set of charms filtered by tag.
    """
    build_env = BuildEnv(build_type=BuildType.CHARM)
    build_env.db["build_args"] = {
        "job_list": charm_list,
        "filter_by_tag": filter_by_tag.split(","),
        "to_channel": to_channel,
        "from_channel": from_channel,
        "track": track,
    }
    build_env.clean()
    return build_env.promote_all(
        from_channel=from_channel, to_channels=build_env.to_channels, dry_run=dry_run
    )


if __name__ == "__main__":
    cli()
