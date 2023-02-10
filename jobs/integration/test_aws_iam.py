import asyncio
import contextlib
import pytest
import random
import json
from pathlib import Path
from .logger import log
from .utils import juju_run
from subprocess import check_output
from shlex import split
from configparser import ConfigParser
from cilib.run import capture
import os


@pytest.fixture(scope="module")
def arn():
    log("Adding AWS IAM Role KubernetesAdmin")

    policy = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Resource": os.environ["AWSIAMARN"],
                "Action": "sts:AssumeRole",
                "Condition": {},
            }
        ],
    }
    log(f"Role Policy {policy}")
    arn = capture(
        [
            "aws",
            "iam",
            "create-role",
            "--role-name",
            "KubernetesAdmin",
            "--description",
            "Kubernetes administrator role (for AWS IAM Authenticator for Kubernetes).",
            "--assume-role-policy-document",
            json.dumps(policy),
            "--output",
            "text",
            "--query",
            "Role.Arn",
        ]
    )
    log(f"Created arn: {arn}")
    yield arn.stdout.decode().strip()


def get_test_keys():
    creds = ConfigParser()
    creds.read(Path("~/.aws/credentials").expanduser())
    if "default" not in creds.sections():
        raise Exception("Could not find default aws credentials")
    key_id = creds["default"]["aws_access_key_id"]
    key = creds["default"]["aws_secret_access_key"]
    return {"id": key_id, "key": key}


async def run_auth(one_control_plane, args):
    creds = get_test_keys()
    cmd = "AWS_ACCESS_KEY_ID={} AWS_SECRET_ACCESS_KEY={} \
           /snap/bin/kubectl --context=aws-iam-authenticator \
           --kubeconfig /home/ubuntu/aws-kubeconfig \
           {}".format(
        creds["id"], creds["key"], args
    )
    output = await juju_run(one_control_plane, cmd, check=False, timeout=15)
    assert output.status == "completed"
    return output.stderr.lower()


async def verify_auth_success(one_control_plane, args):
    error_text = await run_auth(one_control_plane, args)
    assert "invalid user credentials" not in error_text
    assert "error" not in error_text
    assert "forbidden" not in error_text


async def verify_auth_failure(one_control_plane, args):
    error_text = await run_auth(one_control_plane, args)
    assert (
        "invalid user credentials" in error_text
        or "error" in error_text
        or "forbidden" in error_text
        or "accessdenied" in error_text
    )


async def patch_kubeconfig_and_verify_aws_iam(one_control_plane, arn):
    log("patching and validating generated kubectl config file")
    for i in range(6):
        output = await juju_run(one_control_plane, "cat /home/ubuntu/config")
        if "aws-iam-user" in output.stdout:
            await juju_run(
                one_control_plane, "cp /home/ubuntu/config /home/ubuntu/aws-kubeconfig"
            )
            cmd = (
                "sed -i 's;<<insert_arn_here>>;{};'"
                " /home/ubuntu/aws-kubeconfig".format(arn)
            )
            await juju_run(one_control_plane, cmd)
            break
        log("Unable to find AWS IAM information in kubeconfig, retrying...")
        await asyncio.sleep(10)
    assert "aws-iam-user" in output.stdout


@contextlib.asynccontextmanager
async def aws_iam_charm(model, tools):
    orig_deployed = "aws-iam" in model.applications
    if not orig_deployed:
        log("deploying aws-iam")
        await model.deploy("aws-iam", channel=tools.charm_channel, num_units=0)
        await model.add_relation("aws-iam", "kubernetes-control-plane")
        await model.add_relation("aws-iam", "easyrsa")
        log("waiting for cluster to settle...")
    await tools.juju_wait()
    try:
        yield
    finally:
        if not orig_deployed:
            await model.applications["aws-iam"].destroy()


async def test_validate_aws_iam(model, tools):
    # This test verifies the aws-iam charm is working
    # properly. This requires:
    # 1) Deploy aws-iam and relate
    # 2) Deploy CRD
    # 3) Grab new kubeconfig from control-plane.
    # 4) Plug in test ARN to config
    # 5) Download aws-iam-authenticator binary
    # 6) Verify authentication via aws user
    # 7) Turn on RBAC
    # 8) Verify unauthorized access
    # 9) Grant access via RBAC
    # 10) Verify access

    log("starting aws-iam test")
    controllers = model.applications["kubernetes-control-plane"]
    k8s_version_str = controllers.data["workload-version"]
    k8s_minor_version = tuple(int(i) for i in k8s_version_str.split(".")[:2])
    if k8s_minor_version < (1, 15):
        log("skipping, k8s version v" + k8s_version_str)
        return

    # 1) deploy
    await controllers.set_config({"authorization-mode": "AlwaysAllow"})
    async with aws_iam_charm(model, tools):
        # 2) deploy CRD for test
        log("deploying crd")
        cmd = """/snap/bin/kubectl --kubeconfig /root/.kube/config apply -f - << EOF
apiVersion: iamauthenticator.k8s.aws/v1alpha1
kind: IAMIdentityMapping
metadata:
  name: kubernetes-admin
spec:
  arn: {}
  username: test-user
  groups:
  - view
EOF""".format(
            os.environ["AWSIAMARN"]
        )
        # Note that we patch a single controllers's kubeconfig to have the arn in it,
        # so we need to use that one controllers for all commands
        one_control_plane = random.choice(controllers.units)
        output = await juju_run(one_control_plane, cmd, check=False, timeout=15)
        assert output.status == "completed"

        # 3 & 4) grab config and verify aws-iam is inside
        log("verifying kubeconfig")
        await patch_kubeconfig_and_verify_aws_iam(
            one_control_plane, os.environ["AWSIAMARN"]
        )

        # 5) get aws-iam-authenticator binary
        log("getting aws-iam binary")
        cmd = "curl -s https://api.github.com/repos/kubernetes-sigs/aws-iam-authenticator/releases/latest"
        data = json.loads(check_output(split(cmd)).decode("utf-8"))
        for asset in data["assets"]:
            if "linux_amd64" in asset["browser_download_url"]:
                latest_release_url = asset["browser_download_url"]
                break

        auth_bin = "/usr/local/bin/aws-iam-authenticator"
        cmd = "wget -q -nv -O {} {}"
        output = await juju_run(
            one_control_plane, cmd.format(auth_bin, latest_release_url), timeout=15
        )
        assert output.status == "completed"

        output = await juju_run(
            one_control_plane, "chmod a+x {}".format(auth_bin), timeout=15
        )
        assert output.status == "completed"

        # 6) Auth as a user - note that creds come in the environment as a
        #    jenkins secret
        await verify_auth_success(one_control_plane, "get po")

        # 7) turn on RBAC and add a test user
        await controllers.set_config({"authorization-mode": "RBAC,Node"})
        log("waiting for cluster to settle...")
        await tools.juju_wait()

        # 8) verify failure
        await verify_auth_failure(one_control_plane, "get po")

        # 9) grant user access
        cmd = """/snap/bin/kubectl --kubeconfig /root/.kube/config apply -f - << EOF
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: pod-reader
rules:
- apiGroups: [""]
  resources:
  - pods
  verbs:
  - get
  - list
  - watch

---
apiVersion: rbac.authorization.k8s.io/v1
# This role binding allows "test-user" to read pods in the "default" namespace.
kind: RoleBinding
metadata:
  name: read-pods
  namespace: default
subjects:
- kind: User
  name: test-user
  apiGroup: rbac.authorization.k8s.io
roleRef:
  kind: Role
  name: pod-reader
  apiGroup: rbac.authorization.k8s.io
EOF"""
        output = await juju_run(one_control_plane, cmd, timeout=15)
        assert output.status == "completed"

        # 10) verify success
        await verify_auth_success(one_control_plane, "get po")

        # 11) verify overstep failure
        await verify_auth_failure(one_control_plane, "get po -n kube-system")
