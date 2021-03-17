class ExecutorInterface:
    """
    Interface with the low level operations we want to perform on the
    respective substrate.
    """

    def remove_microk8s_directory(self):
        """
        Remove any preexisting microk8s directory
        """
        pass

    def clone_microk8s_repo(self):
        """
        Clone the microk8s project
        """
        pass

    def has_tests_for_track(self, track):
        """
        Are there any tests for the provided track?

        Args:
            track: the track to get the tests from
        """
        pass

    def checkout_branch(self, branch):
        """
        Checkout a specific branch

        Args:
            branch: branch to checkout
        """
        pass

    def set_version_to_build(self, version):
        """
        Set what version we should build

        Args:
            version: version to build
        """
        pass

    def build_snap(self):
        """
        Build the snap from the code we checked out
        """
        pass

    def fetch_created_snap(self, arch=None):
        """
        Fetch the build artifact. The snap should be named microk8s_latest_{arch}.snap

        Args:
            arch: what architecture should we fetch
        """
        pass

    def test_distro(
        self, distro, track_channel_to_upgrade, testing_track_channel, proxy=None
    ):
        """
        Run the MicroK8s tests, by running the test-distro.sh script providing the
        arguments passed here.

        Args:
            distro: distribution to test
            track_channel_to_upgrade: what channel we want to upgrade
            testing_track_channel: what track are we testing
            proxy: pass any proxy arguments to the test script
        """
        pass
