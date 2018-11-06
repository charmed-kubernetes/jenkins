import os
from dateutil import parser
from subprocess import check_output, check_call, CalledProcessError


class Microk8sSnap:

    def __init__(self, track, channel):
        cmd = "snapcraft list-revisions microk8s --arch amd64".split()
        revisions_list = check_output(cmd).decode("utf-8").split("\n")
        if track == "latest":
            channel_patern = " {}*".format(channel)
        else:
            channel_patern = " {}/{}*".format(track, channel)

        revision_info_str = None
        for revision in revisions_list:
            if channel_patern in revision:
                revision_info_str = revision
        if revision_info_str:
            # revision_info_str looks like this:
            # "180     2018-09-12T15:51:33Z  amd64   v1.11.3    1.11/edge*"
            revision_info = revision_info_str.split()

            self.track = track
            self.channel = channel
            self.under_testing_channel = channel
            if "edge" in self.under_testing_channel:
                self.under_testing_channel = "{}/under-testing".format(self.under_testing_channel)
            self.revision = revision_info[0]
            self.version = revision_info[3]
            version_parts = self.version.split('.')
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
        target = channel if self.track == "latest" else "{}/{}".format(self.track, channel)
        cmd = "snapcraft release microk8s {} {}".format(self.revision, target)
        if dry_run == "no":
            check_call(cmd.split())
        else:
            print("DRY RUN - calling: {}".format(cmd))

    def test_cross_distro(self,  channel_to_upgrade='stable',
                          tests_branch=None,
                          distributions = ["ubuntu:16.04", "ubuntu:18.04"]):
        '''
        Test the channel this snap came from and make sure we can upgrade the
        channel_to_upgrade. Tests are run on the distributions distros.

        Args:
            channel_to_upgrade: what channel to try to upgrade
            tests_branch: the branch where tests live. Normally next to the released code.
            distributions: where to run tests on

        '''
        # Get the microk8s source where the tests are. Switch to the branch
        # that matches the track we are going to release to.
        cmd = "rm -rf microk8s".split()
        check_call(cmd)
        cmd = "git clone https://github.com/ubuntu/microk8s".split()
        check_call(cmd)
        os.chdir("microk8s")
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
        cmd = "git checkout {}".format(tests_branch).split()
        check_call(cmd)

        if "under-testing" in self.under_testing_channel:
            self.release_to(self.under_testing_channel)
        for distro in distributions:
            if self.track == "latest":
                track_channel_to_upgrade = channel_to_upgrade
                testing_track_channel = self.under_testing_channel
            else:
                track_channel_to_upgrade = "{}/{}".format(self.track, channel_to_upgrade)
                testing_track_channel = "{}/{}".format(self.track, self.under_testing_channel)

            cmd = "tests/test-distro.sh {} {} {}".format(distro, track_channel_to_upgrade,
                                                         testing_track_channel).split()
            check_call(cmd)
