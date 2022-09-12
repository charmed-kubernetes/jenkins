import click
import configbag
import sh
import os
from dateutil import parser
from subprocess import CalledProcessError, run, PIPE, STDOUT
from executors.juju import JujuExecutor
from executors.local import LocalExecutor
from executors.testflinger import TestFlingerExecutor

sh2 = sh(_iter=True, _err_to_out=True, _env=os.environ.copy())


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
        arch = configbag.get_arch()
        channel_patern = "{}/{}*".format(track, channel)
        if juju_controller:
            click.echo("Using juju executor")
            self.executor = JujuExecutor(juju_unit, juju_controller, juju_model)
        elif testflinger_queue:
            click.echo("Using testflinger executor")
            self.executor = TestFlingerExecutor(testflinger_queue)
        else:
            click.echo("Using local executor")
            self.executor = LocalExecutor()

        self.track = track
        self.channel = channel
        revision_info_str = None

        cmd = "snapcraft list-revisions microk8s --arch {}".format(arch).split()
        click.echo("Callling {}".format(cmd))
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

            self.under_testing_channel = channel
            if "edge" in self.under_testing_channel:
                self.under_testing_channel = "{}/under-testing".format(
                    self.under_testing_channel
                )
            self.revision = revision_info[0]
            self.version = revision_info[3]
            # eksd versions ma look like v1.23-5 so we replace the - with a .
            version_parts = self.version.replace("-", ".").split(".")
            self.is_prerelease = False
            if not version_parts[2].isdigit():
                self.is_prerelease = True
            self.major_minor_version = "{}.{}".format(
                version_parts[0], version_parts[1]
            )
            self.release_date = parser.parse(revision_info[1])
            self.released = True
        else:
            self.released = False

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
        distributions=["ubuntu:18.04"],
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
