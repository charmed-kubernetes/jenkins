"""
snap.py - Building snaps from source and promoting them to snapstore

"""

import click
import yaml
import itertools
import sh
import sys
from pathlib import Path
from cilib import lp, snapapi, html
from cilib.run import cmd_ok


@click.group()
def cli():
    pass


def _promote_snaps(snap_list, arch, from_track, to_track, exclude_pre, dry_run):
    """Promotes snaps from latest revision of version on architecture"""
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
@click.option("--snap-list", help="Path to supported snaps", required=True)
@click.option("--snap-versions", help="Path to supported snap versions", required=True)
@click.option(
    "--owner",
    help="Owner who can access builds",
    required=True,
    default="k8s-jenkaas-admins",
)
def build_summaries(snap_list, snap_versions, owner):
    """Return snap build summaries"""
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
                    "started": (
                        build.date_started.strftime("%Y-%m-%d %H:%M:%S")
                        if build.date_started
                        else "n/a"
                    ),
                    "finished": (
                        build.datebuilt.strftime("%Y-%m-%d %H:%M:%S")
                        if build.datebuilt
                        else "n/a"
                    ),
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
