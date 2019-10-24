import sh
import pytest
import requests
import yaml
from .utils import asyncify, retry_async_with_timeout


def get_pod_yaml():
    out = sh.kubectl.get("po", o="yaml", selector="app=hello-world")
    return yaml.safe_load(out.stdout.decode())


def get_svc_yaml():
    out = sh.kubectl.get("svc", o="yaml", selector="app=hello-world")
    return yaml.safe_load(out.stdout.decode())


async def is_pod_running():
    pod = get_pod_yaml()
    phase = pod["items"][0]["status"]["phase"]
    if "Running" in phase:
        return True
    return False


async def is_pod_cleaned():
    pod = get_pod_yaml()
    if not pod["items"]:
        return True
    return False


@pytest.mark.asyncio
async def test_nodeport_service_endpoint():
    """Create k8s Deployement and NodePort service, send request to NodePort
    """

    try:
        # Create Deployment
        sh.kubectl.create(
            "deployment", "hello-world", image="gcr.io/google-samples/node-hello:1.0"
        )
        sh.kubectl.set("env", "deployment/hello-world", "PORT=50000")

        # Create NodePort Service
        sh.kubectl.expose(
            "deployment",
            "hello-world",
            type="NodePort",
            name="hello-world",
            protocol="TCP",
            port=80,
            target_port=50000,
        )

        # Grab the port
        svc = get_svc_yaml()
        port = svc["items"][0]["spec"]["ports"][0]["nodePort"]

        # Wait for Pods to stabilize
        await retry_async_with_timeout(is_pod_running, ())

        # Grab Pod IP
        pod = get_pod_yaml()
        ip = pod["items"][0]["status"]["hostIP"]

        # Build the url
        set_url = f"http://{ip}:{port}"
        html = await asyncify(requests.get)(set_url)

        assert "Hello Kubernetes!" in html.content.decode()

    finally:
        # Cleanup
        sh.kubectl.delete("deployment", "hello-world")
        sh.kubectl.delete("service", "hello-world")
        await retry_async_with_timeout(is_pod_cleaned, ())
