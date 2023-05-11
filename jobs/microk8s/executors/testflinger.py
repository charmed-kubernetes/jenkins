import time
import json
import configbag
import click
import sh
import os
from subprocess import run, PIPE, STDOUT

from executors.executor import ExecutorInterface


class TestFlingerExecutor(ExecutorInterface):
    """
    Execute basic operations on testflinger.
    """

    def __init__(self, queue="nvidia-gfx"):
        """
        queue: the testflinger queue we want to submit the job
        """
        self.repo = "https://{}".format(configbag.github_repo)
        self.tests_branch = "master"
        self.version_to_build = None
        self.queue = queue
        # The manifest we are going to sent to testflinger.
        # We may want to tune this to properly work on the machine we get from the selected queue
        self.test_manifest = """
job_queue: {}
provision_data:
  distro: focal
test_data:
  test_cmds: |
    set -eux
    ssh $DEVICE_IP <<EOF
      set -eux
      lxd init --auto
      /usr/bin/git clone https://{}
      cd microk8s
      /usr/bin/git checkout {}
      ./tests/test-distro.sh {} {} {} {}
    EOF
"""

    def remove_microk8s_directory(self):
        pass

    def clone_microk8s_repo(self):
        pass

    def has_tests_for_track(self, track):
        cmd = (
            "git ls-remote --exit-code "
            "--heads https://{}.git refs/heads/{}".format(
                configbag.github_repo, track
            ).split()
        )
        run(cmd, check=True, stdout=PIPE, stderr=STDOUT)

    def checkout_branch(self, branch):
        self.tests_branch = branch

    def set_version_to_build(self, version):
        self.version_to_build = version

    def build_snap(self):
        raise NotImplementedError

    def fetch_created_snap(self, arch=None):
        raise NotImplementedError

    def test_distro(
        self, distro, track_channel_to_upgrade, testing_track_channel, proxy=None
    ):
        """
        Submit a testflinger job to the selected queue and raise an exception if the job fails
        """
        fname = "testflinger-job.yaml"
        proxy_ep = "" if not proxy else proxy
        manifest = self.test_manifest.format(
            configbag.github_repo,
            self.queue,
            self.tests_branch,
            distro,
            track_channel_to_upgrade,
            testing_track_channel,
            proxy_ep,
        )
        f = open(fname, "w")
        f.write(manifest)
        f.close()

        cmd = "testflinger submit {}".format(fname)
        job_output = run(cmd.split(), stdout=PIPE, stderr=STDOUT)
        # the raw output looks like this 'Job submitted successfully!\njob_id: 2e2c0cf8-9833-44bb-b55b-371590a91e84\n'
        # we need only the job id
        job_output = job_output.stdout.decode("utf-8").split("\n")
        click.echo("Job submited:\n{}".format(job_output))
        job_output = job_output[1].split()
        job_id = job_output[-1]
        click.echo("Job id: {}".format(job_id))

        status = "pending"
        while "complete" not in status:
            # We do an active wait here instead of calling 'testflinger poll' because
            # poll may not porduce output and the jenkins job may failed because of that.
            click.echo("Waiting for job to complete, current status {}".format(status))
            cmd = "testflinger status {}".format(job_id)
            status_result = run(cmd.split(), stdout=PIPE, stderr=STDOUT)
            status = status_result.stdout.decode("utf-8")
            time.sleep(30)

        cmd = "testflinger results {}".format(job_id)
        job_output = run(cmd.split(), stdout=PIPE, stderr=STDOUT)
        click.echo("Job output: {}".format(job_output.stdout.decode("utf-8")))
        data = json.loads(job_output.stdout.decode("utf-8"))
        if data["test_status"] != "0":
            raise Exception("Job failed with exit code {}".format(data["test_status"]))
