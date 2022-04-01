import click
import sh
import os
from subprocess import run, PIPE, STDOUT, Popen

import configbag
from executors.executor import ExecutorInterface

sh2 = sh(_iter=True, _err_to_out=True, _env=os.environ.copy())


class LocalExecutor(ExecutorInterface):
    """
    Execute the low level operations on local host.
    """

    def remove_microk8s_directory(self):
        cmd = "rm -rf microk8s"
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
        wd = os.getcwd()
        os.chdir("microk8s")
        cmd = "git checkout {}".format(branch)
        self._run_cmd(cmd)
        os.chdir(wd)

    def set_version_to_build(self, version):
        cmd_array = [
            "sed",
            "-i",
            "/^set.*/a export KUBE_VERSION={}".format(version),
            "microk8s/build-scripts/set-env-variables.sh",
        ]
        sh2.env(cmd_array)

    def build_snap(self):
        wd = os.getcwd()
        os.chdir("microk8s")
        cmd = "/snap/bin/snapcraft --use-lxd"
        self._run_cmd(cmd)
        os.chdir(wd)

    def fetch_created_snap(self, arch=None):
        if not arch:
            arch = configbag.get_arch()
        cmd = "mv microk8s/microk8s_*_{0}.snap microk8s_latest_{0}.snap".format(arch)
        Popen(cmd, shell=True, stdout=PIPE, stderr=PIPE)

    def test_distro(
        self, distro, track_channel_to_upgrade, testing_track_channel, proxy=None
    ):
        wd = os.getcwd()
        os.chdir("microk8s")
        cmd = "tests/test-distro.sh {} {} {}".format(
            distro, track_channel_to_upgrade, testing_track_channel
        )
        if proxy:
            cmd = "{} {}".format(cmd, proxy)
        self._run_cmd(cmd)
        os.chdir(wd)

    def _run_cmd(self, cmd):
        click.echo("Executing: {}".format(cmd))
        for line in sh2.env(cmd.split()):
            click.echo(line.strip())
