import configbag
from dateutil import parser
from subprocess import check_output, check_call, CalledProcessError


class Microk8sSnap:

    def __init__(self, track, channel, juju_unit=None, juju_controller=None):
        arch = configbag.get_arch()
        cmd = "snapcraft list-revisions microk8s --arch {}".format(arch).split()
        revisions_list = check_output(cmd).decode("utf-8").split("\n")
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
                self.under_testing_channel = "{}/under-testing".format(self.under_testing_channel)
            self.revision = revision_info[0]
            self.version = revision_info[3]
            version_parts = self.version.split('.')
            self.is_prerelease = False
            if not version_parts[2].isdigit():
                self.is_prerelease = True
            self.major_minor_version = "{}.{}".format(version_parts[0], version_parts[1])
            self.release_date = parser.parse(revision_info[1])
            self.released = True
        else:
            self.released = False

    def release_to(self, channel, dry_run="no"):
        '''
        Release the Snap to the input channel
        Args:
            channel: The channel to release to

        '''
        if self.is_prerelease:
            print("This is a pre-release {}. Cannot release to other channels.".format(self.revision))
            raise Exception("Cannot release pre-releases.")
        target = channel if self.track == "latest" else "{}/{}".format(self.track, channel)
        cmd = "snapcraft release microk8s {} {}".format(self.revision, target)
        if dry_run == "no":
            check_call(cmd.split())
        else:
            print("DRY RUN - calling: {}".format(cmd))

    def test_cross_distro(self,  channel_to_upgrade='stable',
                          tests_branch=None,
                          distributions=["ubuntu:16.04", "ubuntu:18.04"],
                          proxy=None):
        '''
        Test the channel this snap came from and make sure we can upgrade the
        channel_to_upgrade. Tests are run on the distributions distros.

        Args:
            channel_to_upgrade: what channel to try to upgrade
            tests_branch: the branch where tests live. Normally next to the released code.
            distributions: where to run tests on
            proxy: Proxy URL to pass to the tests

        '''
        # Get the microk8s source where the tests are. Switch to the branch
        # that matches the track we are going to release to.
        cmd = "rm -rf microk8s"
        cmd_array = self.cmd_array_to_run(cmd)
        check_call(cmd_array)

        cmd = "git clone https://github.com/ubuntu/microk8s"
        cmd_array = self.cmd_array_to_run(cmd)
        check_call(cmd_array)

        if not tests_branch:
            if self.track == 'latest':
                tests_branch = 'master'
            else:
                # See if we have tests for the track we are using. If not, we should default to master branch.
                # This may happen for the tracks that are building from master GH branch.
                cmd = "git ls-remote --exit-code " \
                      "--heads https://github.com/ubuntu/microk8s.git {}".format(self.track).split()
                try:
                    check_call(cmd)
                    tests_branch = self.track
                except CalledProcessError:
                    print("GH branch {} does not exist.".format(self.track))
                    tests_branch = 'master'
        print("Tests are taken from branch {}".format(tests_branch))
        cmd = "(cd microk8s; git checkout {})".format(tests_branch)
        cmd_array = self.cmd_array_to_run(cmd)
        check_call(cmd_array)

        if "under-testing" in self.under_testing_channel:
            self.release_to(self.under_testing_channel)
        for distro in distributions:
            if self.track == "latest":
                track_channel_to_upgrade = channel_to_upgrade
                testing_track_channel = self.under_testing_channel
            else:
                track_channel_to_upgrade = "{}/{}".format(self.track, channel_to_upgrade)
                testing_track_channel = "{}/{}".format(self.track, self.under_testing_channel)

            cmd = "sudo tests/test-distro.sh {} {} {}".format(distro, track_channel_to_upgrade,
                                                              testing_track_channel)
            if proxy:
                cmd = "{} {}".format(cmd, proxy)
            cmd = "(cd microk8s; {} )".format(cmd)
            cmd_array = self.cmd_array_to_run(cmd)
            check_call(cmd_array)

    def build_and_release(self,  release=None, dry_run="no"):
        '''
        Build and release the snap from release.

        Args:
            release: what k8s version to package
            dry_run: if "no" do the actual release
        '''
        cmd = "rm -rf microk8s"
        cmd_array = self.cmd_array_to_run(cmd)
        check_call(cmd_array)

        cmd = "git clone https://github.com/ubuntu/microk8s"
        cmd_array = self.cmd_array_to_run(cmd)
        check_call(cmd_array)

        if release:
            if not release.startswith('v'):
                release = "v{}".format(release)
            cmd = "sed -i '/^set.*/a export KUBE_VERSION={}' microk8s/build-scripts/prepare-env.sh".format(release)
            if self.juju_controller:
                cmd_array = self.cmd_array_to_run(cmd)
            else:
                cmd_array = ["sed", "-i", "/^set.*/a export KUBE_VERSION={}".format(release), "microk8s/build-scripts/prepare-env.sh"]
            check_call(cmd_array)

        cmd = "(cd microk8s; sudo /snap/bin/snapcraft cleanbuild)"
        cmd_array = self.cmd_array_to_run(cmd)
        check_call(cmd_array)

        cmd = "rm -rf microk8s_latest_amd64.snap"
        check_call(cmd.split())
        if self.juju_controller:
            cmd = "juju  scp -m {} {}:/var/lib/juju/agents/unit-ubuntu-0/charm/microk8s/microk8s_latest_amd64.snap ."\
                .format(self.juju_controller, self.juju_unit)
            check_call(cmd.split())
        else:
            cmd = "mv microk8s/microk8s_latest_amd64.snap ."
            check_call(cmd.split())

        target = "{}/{}".format(self.track, self.channel)
        cmd = "snapcraft push microk8s_latest_amd64.snap --release {}".format(target)
        if dry_run == "no":
            check_call(cmd.split())
        else:
            print("DRY RUN - calling: {}".format(cmd))

        cmd = "rm -rf microk8s_latest_amd64.snap"
        check_call(cmd.split())

    def cmd_array_to_run(self, cmd):
        '''
        Return the cmd array needed to execute the command provided.
        The returned array should be applicable for running the command with juju run.

        Args:
            cmd: the command we wish to execute

        '''
        if self.juju_unit:
            cmd_array = "juju run -m {} --timeout=60m0s --unit {}".format(self.juju_controller, self.juju_unit).split()
            cmd_array.append(cmd)
        else:
            cmd_array = cmd.split()
        return cmd_array
