import click
import sh
import os
from subprocess import run, PIPE, STDOUT, CalledProcessError

import configbag
from executors.executor import ExecutorInterface


class JujuExecutor(ExecutorInterface):
    """
    Run tests on a juju machine already provisioned
    """

    def __init__(self, unit, controller, model):
        """
        Specify the controller, model and unit we will be running the tests on
        """
        self.unit = unit
        self.controller = controller
        self.model = model

    def remove_microk8s_directory(self):
        cmd = "sudo rm -rf microk8s"
        self._run_cmd(cmd)

    def clone_microk8s_repo(self):
        cmd = "git clone https://{}".format(configbag.github_repo)
        self._run_cmd(cmd)

    def has_tests_for_track(self, track):
        cmd = (
            "git ls-remote --exit-code "
            "--heads https://{}.git refs/heads/{}".format(
                configbag.github_repo, track
            ).split()
        )
        run(cmd, check=True, stdout=PIPE, stderr=STDOUT)

    def checkout_branch(self, branch):
        cmd = "(cd microk8s; git checkout {})".format(branch)
        self._run_cmd(cmd)

    def set_version_to_build(self, version):
        cmd = "sed -i 's/^KUBE_VERSION=.*/KUBE_VERSION={}/' microk8s/build-scripts/components/kubernetes/version.sh".format(
            version
        )
        self._run_cmd(cmd)

    def build_snap(self):
        cmd = '(cd microk8s; pwd; sudo usermod --append --groups lxd $USER; sg lxd -c "SNAPCRAFT_BUILD_ENVIRONMENT=lxd /snap/bin/snapcraft")'
        self._run_cmd(cmd)

    def fetch_created_snap(self, arch=None):
        if not arch:
            arch = configbag.get_arch()
        cmd = (
            "juju  scp -m {}:{} "
            "{}:/home/ubuntu/microk8s/microk8s_*_{}.snap microk8s_latest_{}.snap".format(
                self.controller, self.model, self.unit, arch, arch
            )
        )
        try:
            run(cmd.split(), check=True, stdout=PIPE, stderr=STDOUT)
        except CalledProcessError as err:
            click.echo(err.output)
            raise err

    def test_distro(
        self, distro, track_channel_to_upgrade, testing_track_channel, proxy=None
    ):
        cmd = "sudo DISABLE_COMMUNITY_TESTS=1 tests/test-distro.sh {} {} {}".format(
            distro, track_channel_to_upgrade, testing_track_channel
        )
        if proxy:
            cmd = "{} {}".format(cmd, proxy)
        cmd = "(cd microk8s; {} )".format(cmd)
        self._run_cmd(cmd)

    def _run_cmd(self, cmd):
        juju_ssh = sh.juju.ssh.bake(m=f"{self.controller}:{self.model}", pty="true")
        unit_ssh = juju_ssh.bake(
            self.unit, _iter=True, _err_to_out=True, _env=os.environ.copy()
        )
        click.echo(f"Executing: {unit_ssh} -- {cmd}")
        for line in unit_ssh(cmd):
            click.echo(line.strip())
