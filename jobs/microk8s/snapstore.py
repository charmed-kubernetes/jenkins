import click
import configbag
import sh
import os
from dateutil import parser
from subprocess import check_output, check_call, CalledProcessError, run, PIPE, STDOUT

sh2 = sh(_iter=True, _err_to_out=True, _env=os.environ.copy())


class Microk8sSnap:
    def __init__(self, track, channel, juju_unit=None, juju_controller=None):
        arch = configbag.get_arch()
        cmd = "snapcraft list-revisions microk8s --arch {}".format(arch).split()
        revisions_list = run(cmd, stdout=PIPE, stderr=STDOUT)
        revisions_list = revisions_list.stdout.decode("utf-8").split("\n")
        if track == "latest":
            channel_patern = " {}*".format(channel)
        else:
            channel_patern = " {}/{}*".format(track, channel)

        self.juju_unit = juju_unit
        self.juju_controller = juju_controller
        self.track = track
        self.channel = channel
        revision_info_str = None
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
            version_parts = self.version.split(".")
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

    def release_to(self, channel, dry_run="no"):
        """
        Release the Snap to the input channel
        Args:
            channel: The channel to release to

        """
        if self.is_prerelease:
            click.echo(
                "This is a pre-release {}. Cannot release to other channels.".format(
                    self.revision
                )
            )
            raise Exception("Cannot release pre-releases.")
        target = "{}/{}".format(self.track, channel)
        cmd = "snapcraft release microk8s {} {}".format(self.revision, target)
        if dry_run == "no":
            run(cmd.split(), check=True, stdout=PIPE, stderr=STDOUT)
        else:
            click.echo("DRY RUN - calling: {}".format(cmd))

    def test_cross_distro(
        self,
        channel_to_upgrade="latest/stable",
        tests_branch=None,
        distributions=["ubuntu:16.04", "ubuntu:18.04"],
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
        cmd = "rm -rf microk8s"
        cmd_array = self.cmd_array_to_run(cmd)
        for line in sh2.env(cmd_array):
            click.echo(line.strip())

        cmd = "git clone https://github.com/ubuntu/microk8s"
        cmd_array = self.cmd_array_to_run(cmd)
        for line in sh2.env(cmd_array):
            click.echo(line.strip())

        if not tests_branch:
            if self.track == "latest":
                tests_branch = "master"
            else:
                # See if we have tests for the track we are using. If not, we should default to master branch.
                # This may happen for the tracks that are building from master GH branch.
                cmd = (
                    "git ls-remote --exit-code "
                    "--heads https://github.com/ubuntu/microk8s.git {}".format(
                        self.track
                    ).split()
                )
                try:
                    run(cmd, check=True, stdout=PIPE, stderr=STDOUT)
                    tests_branch = self.track
                except CalledProcessError:
                    click.echo("GH branch {} does not exist.".format(self.track))
                    tests_branch = "master"
        click.echo("Tests are taken from branch {}".format(tests_branch))
        cmd = "(cd microk8s; git checkout {})".format(tests_branch)
        cmd_array = self.cmd_array_to_run(cmd)
        for line in sh2.env(cmd_array):
            click.echo(line.strip())

        if "under-testing" in self.under_testing_channel:
            self.release_to(self.under_testing_channel)
        for distro in distributions:
            track_channel_to_upgrade = "{}/{}".format(self.track, channel_to_upgrade)
            testing_track_channel = "{}/{}".format(
                self.track, self.under_testing_channel
            )

            cmd = "sudo tests/test-distro.sh {} {} {}".format(
                distro, track_channel_to_upgrade, testing_track_channel
            )
            if proxy:
                cmd = "{} {}".format(cmd, proxy)
            cmd = "(cd microk8s; {} )".format(cmd)
            cmd_array = self.cmd_array_to_run(cmd)
            for line in sh2.env(cmd_array):
                click.echo(line.strip())

    def build_and_release(self, release=None, dry_run="no"):
        """
        Build and release the snap from release.

        Args:
            release: what k8s version to package
            dry_run: if "no" do the actual release
        """
        arch = configbag.get_arch()
        cmd = "rm -rf microk8s"
        cmd_array = self.cmd_array_to_run(cmd)
        for line in sh2.env(cmd_array):
            click.echo(line.strip())

        cmd = "git clone https://github.com/ubuntu/microk8s"
        cmd_array = self.cmd_array_to_run(cmd)
        for line in sh2.env(cmd_array):
            click.echo(line.strip())

        if release:
            if not release.startswith("v"):
                release = "v{}".format(release)
            cmd = "sed -i '/^set.*/a export KUBE_VERSION={}' microk8s/build-scripts/set-env-variables.sh".format(
                release
            )
            if self.juju_controller:
                cmd_array = self.cmd_array_to_run(cmd)
            else:
                cmd_array = [
                    "sed",
                    "-i",
                    "/^set.*/a export KUBE_VERSION={}".format(release),
                    "microk8s/build-scripts/set-env-variables.sh",
                ]
            for line in sh2.env(cmd_array):
                click.echo(line.strip())

        cmd = '(cd microk8s; pwd; sudo usermod --append --groups lxd $USER; sg lxd -c "SNAPCRAFT_BUILD_ENVIRONMENT=lxd /snap/bin/snapcraft")'
        cmd_array = self.cmd_array_to_run(cmd)
        for line in sh2.env(cmd_array):
            click.echo(line.strip())

        cmd = "rm -rf microk8s_latest_{}.snap".format(arch)
        run(cmd.split(), check=True, stdout=PIPE, stderr=STDOUT)
        if self.juju_controller:
            _model = os.environ.get("JUJU_MODEL")
            cmd = (
                "juju  scp -m {}:{} "
                "{}:/home/ubuntu/microk8s/microk8s_*_{}.snap microk8s_latest_{}.snap".format(
                    self.juju_controller, _model, self.juju_unit, arch, arch
                )
            )
            try:
                run(cmd.split(), check=True, stdout=PIPE, stderr=STDOUT)
            except CalledProcessError as err:
                click.echo(err.output)
                raise err
        else:
            cmd = "mv microk8s/microk8s_*_{}.snap microk8s_latest_{}.snap".format(
                arch, arch
            )
            run(cmd.split(), check=True, stdout=PIPE, stderr=STDOUT)

        target = "{}/{}".format(self.track, self.channel)
        cmd = "snapcraft push microk8s_latest_{}.snap --release {}".format(arch, target)
        if dry_run == "no":
            run(cmd.split(), check=True, stdout=PIPE, stderr=STDOUT)
        else:
            click.echo("DRY RUN - calling: {}".format(cmd))

        cmd = "rm -rf microk8s_latest_{}.snap".format(arch)
        run(cmd.split(), check=True, stdout=PIPE, stderr=STDOUT)

    def cmd_array_to_run(self, cmd):
        """
        Return the cmd array needed to execute the command provided.
        The returned array should be applicable for running the command with juju run.

        Args:
            cmd: the command we wish to execute

        """
        if self.juju_unit:
            import os
            import json
            import shlex

            _controller = os.environ.get("JUJU_CONTROLLER")
            _model = os.environ.get("JUJU_MODEL")
            cmd_array = shlex.split(
                f"juju ssh -m {_controller}:{_model} --pty=true ubuntu/0 --"
            )
            # cmd_array = "juju run -m {}:{} --timeout=120m0s --unit {}".format(
            #     _controller, _model, self.juju_unit
            # ).split()
            cmd_array.append(cmd)
        else:
            cmd_array = cmd.split()
        click.echo("Executing: {}".format(cmd_array))
        return cmd_array
