import click
import sh
import os
import shlex
from pathlib import Path
from subprocess import run, PIPE, STDOUT, Popen

import configbag
from executors.executor import ExecutorInterface


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
        cmd = "git checkout {}".format(branch)
        self._run_cmd(cmd, _cwd=Path("microk8s"))

    def set_version_to_build(self, version):
        sh.sed(
            "-i",
            "s/KUBE_VERSION=.*/KUBE_VERSION={version}/"
            "microk8s/build-scripts/components/kubernetes/version.sh",
        )

    def build_snap(self):
        cmd = "/snap/bin/snapcraft --use-lxd"
        self._run_cmd(cmd, _cwd=Path("microk8s"))

    def fetch_created_snap(self, arch=None):
        if not arch:
            arch = configbag.get_arch()
        cmd = "mv microk8s/microk8s_*_{0}.snap microk8s_latest_{0}.snap".format(arch)
        Popen(cmd, shell=True, stdout=PIPE, stderr=PIPE)

    def test_distro(
        self, distro, track_channel_to_upgrade, testing_track_channel, proxy=None
    ):
        cmd = "DISABLE_COMMUNITY_TESTS=1 tests/test-distro.sh {} {} {}".format(
            distro, track_channel_to_upgrade, testing_track_channel
        )
        if proxy:
            cmd = "{} {}".format(cmd, proxy)
        self._run_cmd(cmd, _cwd=Path("microk8s"))

    def _run_cmd(self, cmd, _cwd=Path()):
        prog, *args = shlex.split(cmd)
        local_run = getattr(sh, prog).bake(
            *args, _iter=True, _err_to_out=True, _env=os.environ.copy(), _cwd=_cwd
        )
        click.echo(f"Executing: {cmd}")
        for line in local_run():
            click.echo(line.strip())
