class ExecutorInterface:
    def remove_microk8s_directory(self):
        pass

    def clone_microk8s_repo(self):
        pass

    def has_tests_for_track(self, track):
        pass

    def checkout_branch(self, branch):
        pass

    def set_version_to_build(self, version):
        pass

    def build_snap(self):
        pass

    def fetch_created_snap(self, arch=None):
        pass

    def test_distro(
        self, distro, track_channel_to_upgrade, testing_track_channel, proxy=None
    ):
        pass
