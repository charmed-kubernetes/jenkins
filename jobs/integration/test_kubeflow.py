import asyncio
import os
from subprocess import check_output

import pytest
import requests

from .base import UseModel
from .logger import log_calls, log_calls_async
from .utils import asyncify


def get_ambassador_ip():
    """Returns the Ambassador IP address."""

    with open('../PUB_IP') as f:
        return f'{f.read().strip()}.xip.io'


@pytest.mark.asyncio
async def test_validate(log_dir):
    """Validates a Kubeflow deployment"""

    async with UseModel() as model:
        # Synchronously check what juju thinks happened
        validate_statuses(model)

        # Asynchronously check everything else concurrently
        await asyncio.gather(
            validate_ambassador(), validate_jupyterhub_api(), validate_tf_dashboard()
        )


@log_calls
def validate_statuses(model):
    """Validates that a known set of units have booted up into the correct state."""

    expected_units = {
        "kubeflow-ambassador/0",
        "kubeflow-jupyterhub/0",
        "kubeflow-tf-job-dashboard/0",
        "kubeflow-tf-job-operator/0",
    }

    assert set(model.units.keys()) == expected_units

    for unit in model.units.values():
        assert unit.agent_status == "idle"
        assert unit.workload_status == "active"
        assert unit.workload_status_message == ""


@log_calls_async
async def validate_ambassador():
    """Validates that the ambassador is up and responding."""

    checks = {
        "/ambassador/v0/check_ready": b"ambassador readiness check OK",
        "/ambassador/v0/check_alive": b"ambassador liveness check OK",
    }

    ambassador_ip = get_ambassador_ip()

    for endpoint, text in checks.items():
        resp = await asyncify(requests.get)(f"http://{ambassador_ip}{endpoint}")
        resp.raise_for_status()
        assert resp.content.startswith(text)


@log_calls_async
async def validate_jupyterhub_api():
    """Validates that JupyterHub is up and responding via Ambassador."""

    ambassador_ip = get_ambassador_ip()

    resp = await asyncify(requests.get)(f"http://{ambassador_ip}/hub/api/")
    resp.raise_for_status()
    assert list(resp.json().keys()) == ["version"]


def submit_tf_job(name: str):
    """Submits a TFJob to the TensorFlow Job service."""

    output = check_output(
        [
            "microk8s.kubectl",
            "--kubeconfig",
            "../kube_config",
            "create",
            "-n",
            os.environ["MODEL"],
            "-f",
            f"../tfjobs/{name}/job.yaml",
        ]
    ).strip()

    assert output == f"tfjob.kubeflow.org/kubeflow-{name}-test created".encode("utf-8")


@log_calls_async
async def validate_tf_dashboard():
    """Validates that TF Jobs dashboard is up and responding via Ambassador."""

    ambassador_ip = get_ambassador_ip()

    await asyncify(submit_tf_job)("mnist")

    expected_jobs = [("PS", 1), ("Worker", 1)]
    expected_conditions = [
        ("Created", "True", "TFJobCreated", "TFJob kubeflow-mnist-test is created."),
        ("Running", "False", "TFJobRunning", "TFJob kubeflow-mnist-test is running."),
        (
            "Succeeded",
            "True",
            "TFJobSucceeded",
            "TFJob kubeflow-mnist-test is successfully completed.",
        ),
    ]
    expected_statuses = {"PS": {}, "Worker": {}, "Chief": {}, "Master": {}}

    # Wait for up to 5 minutes for the job to complete,
    # checking every 5 seconds
    for i in range(60):
        resp = await asyncify(requests.get)(f"http://{ambassador_ip}/tfjobs/api/tfjob/")
        resp.raise_for_status()
        response = resp.json()["items"][0]

        jobs = [
            (name, spec["replicas"]) for name, spec in response["spec"]["tfReplicaSpecs"].items()
        ]

        conditions = [
            (cond["type"], cond["status"], cond["reason"], cond["message"])
            for cond in response["status"]["conditions"] or []
        ]

        statuses = response["status"]["tfReplicaStatuses"]

        try:
            assert jobs == expected_jobs
            assert conditions == expected_conditions
            assert expected_statuses == statuses
            break
        except AssertionError as err:
            print("Waiting for TFJob to complete...")
            print(err)
            await asyncio.sleep(5)
    else:
        raise Exception("Waited too long for TFJob to succeed!")
