import click
import configbag
import os
from dateutil import parser
from subprocess import CalledProcessError, run, PIPE, STDOUT
from executors.juju import JujuExecutor
from executors.local import LocalExecutor
from executors.testflinger import TestFlingerExecutor


class Microk8sSnap:
    def __init__(
        self,
        track,
        channel,
        juju_unit=None,
        juju_controller=None,
        juju_model=None,
        testflinger_queue=None,
    ):
        self.track = track
        self.channel = channel

        arch = configbag.get_arch()
        release_info = self._try_list_revisions(track, channel, arch)
        if not release_info[0]:
            # We failed to spot the release information with snapcraft list_revisions
            # lets try the snapcraft status
            release_info = self._try_status(track, channel, arch)

        self.released = release_info[0]
        if release_info[0]:
            click.echo(f"Release date {release_info[1]} revision {release_info[3]}")
            self.under_testing_channel = channel
            if "edge" in self.under_testing_channel:
                self.under_testing_channel = "{}/under-testing".format(
                    self.under_testing_channel
                )
            self.revision = release_info[3]
            self.version = release_info[4]
            self.is_prerelease = release_info[5]
            self.major_minor_version = release_info[2]
            self.release_date = release_info[1]
            self.released = release_info[0]
        else:
            click.echo("Not released")

        if juju_controller:
            click.echo("Using juju executor")
            self.executor = JujuExecutor(juju_unit, juju_controller, juju_model)
        elif testflinger_queue:
            click.echo("Using testflinger executor")
            self.executor = TestFlingerExecutor(testflinger_queue)
        else:
            click.echo("Using local executor")
            self.executor = LocalExecutor()

    def _try_list_revisions(self, track, channel, arch):
        """
        Call 'snapcraft list-revisions' and try to identify the following return values:
        Args:
            track: track we are looking for
            channel: channel to look for
            arch: architecture we are looking for
        Returns:
            a tuple with the following:
            - released, True if we have a release, if we do not have a release the rest are set to None
            - release_date, date of the release
            - major_minor_version, only major and minor version identifiers
            - revision,
            - version, the version string
            - is_prerelease, True is this is a pre-release

        """
        channel_patern = "{}/{}*".format(track, channel)
        revision_info_str = None
        cmd = "snapcraft list-revisions microk8s --arch {}".format(arch).split()

        click.echo("Calling {}".format(cmd))
        revisions_list = run(cmd, stdout=PIPE, stderr=STDOUT)
        revisions_list = revisions_list.stdout.decode("utf-8").split("\n")
        click.echo("Got revisions list with size {}".format(len(revisions_list)))
        click.echo("Searching for {} in revisions list".format(channel_patern))
        for revision in revisions_list:
            if channel_patern in revision:
                revision_info_str = revision
        if revision_info_str:
            # revision_info_str looks like this:
            # "180     2018-09-12T15:51:33Z  amd64   v1.11.3    1.11/edge*"
            revision_info = revision_info_str.split()
            revision = revision_info[0]
            version = revision_info[3]
            is_prerelease, major_minor_version = self._extract_version(version)
            release_date = parser.parse(revision_info[1])
            released = True
            return (
                released,
                release_date,
                major_minor_version,
                revision,
                version,
                is_prerelease,
            )
        else:
            released = False
            return (released, None, None, None, None, None)

    def _try_status(self, track, channel, arch):
        """
        Call 'snapcraft status' and try to identify the following return values:
        Args:
            track: track we are looking for
            channel: channel to look for
            arch: architecture we are looking for
        Returns:
            a tuple with the following:
            - released, True if we have a release, if we do not have a release the rest are set to None
            - release_date, date of the release
            - major_minor_version, only major and minor version identifiers
            - revision,
            - version, the version string
            - is_prerelease, True is this is a pre-release

        """
        cmd = "snapcraft status microk8s --arch {}".format(arch).split()
        click.echo("Calling {}".format(cmd))
        releases_list = run(cmd, stdout=PIPE, stderr=STDOUT)
        releases_list = releases_list.stdout.decode("utf-8").split("\n")
        in_track = False
        released = False
        for line in releases_list:
            if line.startswith(track + " "):
                # adding the extra space after the track to differentiate between 1.25 vs 1.25-strict
                in_track = True
            if in_track == True and not (
                line.startswith(" ") or line.startswith(track + " ")
            ):
                in_track = False
            if in_track:
                # line may look like:
                # "1.25         amd64   stable              v1.25.2          4055        -           -"
                # or it may look like:
                # "                     candidate           v1.25.2          4055        -           -"
                #
                # In the first case we are not interested in the version and architecture
                line_parts = line.split()
                if line_parts[0] == track:
                    assert line_parts.pop(0) == track
                    assert line_parts.pop(0) == arch
                if line_parts[0] == channel:
                    click.echo(line_parts)
                    version = line_parts[1]
                    revision = line_parts[2]
                    # In case of a channel that we do not have released anything yet,
                    # eg in a pre-stable release, we have: the line_parts to be:
                    # ['beta', '↑', '↑']. We detect this case below.
                    if len(version) <= 1 or "." not in version:
                        # Nothing released on this track/channel
                        break
                    is_prerelease, major_minor_version = self._extract_version(version)
                    released = True
                    # set an old date
                    release_date = parser.parse("2015-10-10T00:00:00Z")
                    return (
                        released,
                        release_date,
                        major_minor_version,
                        revision,
                        version,
                        is_prerelease,
                    )

        # we did not find anything
        return (released, None, None, None, None, None)

    def _extract_version(self, version):
        """
        Parse the version parts from a string similar to v1.23.3"
        Args:
            version: the version string to parse
        Return:
            (is_prerelease, major_minor_version) tuple
        """
        # eksd versions ma look like v1.23-5 so we replace the - with a .
        version_parts = version.replace("-", ".").split(".")
        click.echo(version)
        is_prerelease = False
        if len(version_parts) > 3 and not version_parts[3].isdigit():
            is_prerelease = True
        major_minor_version = "{}.{}".format(version_parts[0], version_parts[1])
        return (is_prerelease, major_minor_version)

    def release_to(self, channel, release_to_track=None, dry_run="no"):
        """
        Release the Snap to the input channel
        Args:
            channel: The channel to release to
            release_to_track: the track to release to

        """
        if not release_to_track:
            release_to_track = self.track
        if self.is_prerelease:
            click.echo(
                "This is a pre-release {}. Cannot release to other channels.".format(
                    self.revision
                )
            )
            raise Exception("Cannot release pre-releases.")
        target = "{}/{}".format(release_to_track, channel)
        cmd = "snapcraft release microk8s {} {}".format(self.revision, target)
        if dry_run == "no":
            try:
                click.echo(
                    "Release revision {} to {}".format(self.revision, release_to_track)
                )
                run(cmd.split(), check=True, stdout=PIPE, stderr=STDOUT)
            except CalledProcessError as e:
                click.echo("Release failed: {}".format(e.stdout))
                raise
        else:
            click.echo("DRY RUN - calling: {}".format(cmd))

    def test_cross_distro(
        self,
        channel_to_upgrade=None,
        track_to_upgrade=None,
        tests_branch=None,
        distributions=["ubuntu:20.04"],
        proxy=None,
    ):
        """
        Test the channel this snap came from and make sure we can upgrade the
        channel_to_upgrade. Tests are run on the distributions distros.

        Args:
            channel_to_upgrade: what channel to try to upgrade
            tests_branch: the branch where tests live. Normally next to the released code.
            distributions: where to run tests on
            proxy: Proxy URL to pass to the tests

        """
        # Get the microk8s source where the tests are. Switch to the branch
        # that matches the track we are going to release to.
        self.executor.remove_microk8s_directory()
        self.executor.clone_microk8s_repo()

        if not tests_branch:
            if self.track == "latest":
                tests_branch = "master"  # wokeignore:rule=master
            else:
                # See if we have tests for the track we are using. If not, we should default to master branch.
                # This may happen for the tracks that are building from master GH branch.
                try:
                    self.executor.has_tests_for_track(self.track)
                    tests_branch = self.track
                except CalledProcessError:
                    click.echo("GH branch {} does not exist.".format(self.track))
                    if "strict" in self.track:
                        tests_branch = "strict"
                    else:
                        tests_branch = "master"  # wokeignore:rule=master
        click.echo("Tests are taken from branch {}".format(tests_branch))
        self.executor.checkout_branch(tests_branch)

        if "under-testing" in self.under_testing_channel:
            self.release_to(self.under_testing_channel)
        if not track_to_upgrade:
            track_to_upgrade = self.track
        for distro in distributions:
            track_channel_to_upgrade = "{}/{}".format(
                track_to_upgrade, channel_to_upgrade
            )
            testing_track_channel = "{}/{}".format(
                self.track, self.under_testing_channel
            )
            self.executor.test_distro(
                distro, track_channel_to_upgrade, testing_track_channel, proxy
            )

    def build_and_release(self, release=None, dry_run="no"):
        """
        Build and release the snap from release.

        Args:
            release: what k8s version to package
            dry_run: if "no" do the actual release
        """
        arch = configbag.get_arch()
        self.executor.remove_microk8s_directory()
        self.executor.clone_microk8s_repo()

        if release:
            if not release.startswith("v"):
                release = "v{}".format(release)
            self.executor.set_version_to_build(release)

        if "strict" in self.track:
            self.executor.checkout_branch("strict")

        self.executor.build_snap()

        cmd = "rm -rf microk8s_latest_{}.snap".format(arch)
        run(cmd.split(), check=True, stdout=PIPE, stderr=STDOUT)
        self.executor.fetch_created_snap()

        target = "{}/{}".format(self.track, self.channel)
        cmd = "snapcraft push microk8s_latest_{}.snap --release {}".format(arch, target)
        if dry_run == "no":
            run(cmd.split(), check=True, stdout=PIPE, stderr=STDOUT)
        else:
            click.echo("DRY RUN - calling: {}".format(cmd))

        cmd = "rm -rf microk8s_latest_{}.snap".format(arch)
        run(cmd.split(), check=True, stdout=PIPE, stderr=STDOUT)
