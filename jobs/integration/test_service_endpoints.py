import asyncio
import logging
import sh
import yaml
from .utils import retry_async_with_timeout, juju_run

log = logging.getLogger(__name__)
APP_PORT = 50000
SVC_PORT = 80


def get_pod_yaml():
    out = sh.kubectl.get("po", o="yaml", selector="app=hello-world")
    return yaml.safe_load(out)


def get_svc_yaml():
    out = sh.kubectl.get("svc", o="yaml", selector="app=hello-world")
    return yaml.safe_load(out)


async def is_pod_running():
    pod = get_pod_yaml()

    try:
        phase = pod["items"][0]["status"]["phase"]
        port = pod["items"][0]["spec"]["containers"][0]["env"][0]["value"]
    except (IndexError, KeyError):
        # Pod not created correctly
        return False

    if "Running" in phase and str(APP_PORT) == port:
        return len(pod["items"]) == 1

    # Pod has not fully come up yet
    return False


async def is_pod_cleaned():
    pod = get_pod_yaml()
    if not pod["items"]:
        return True
    return False


async def setup_svc(svc_type):
    # Create Deployment
    sh.kubectl.create(
        "deployment",
        "hello-world",
        image="rocks.canonical.com/cdk/google-samples/hello-app:1.0",
    )
    sh.kubectl.set("env", "deployment/hello-world", f"PORT={APP_PORT}")

    # Create Service
    sh.kubectl.expose(
        "deployment",
        "hello-world",
        type=f"{svc_type}",
        name="hello-world",
        protocol="TCP",
        port=SVC_PORT,
        target_port=APP_PORT,
    )

    # Wait for Pods to stabilize
    await retry_async_with_timeout(
        is_pod_running, (), timeout_msg="Pod(s) failed to stabilize before timeout"
    )


async def cleanup():
    sh.kubectl.delete("deployment", "hello-world")
    sh.kubectl.delete("service", "hello-world")
    await retry_async_with_timeout(
        is_pod_cleaned, (), timeout_msg="Pod(s) failed to clean before timeout"
    )


async def test_nodeport_service_endpoint(tools):
    """Create k8s Deployment and NodePort service, send request to NodePort"""

    try:
        await setup_svc("NodePort")

        # Grab the port
        svc = get_svc_yaml()
        port = svc["items"][0]["spec"]["ports"][0]["nodePort"]

        # Grab Pod IP
        pod = get_pod_yaml()
        ip = pod["items"][0]["status"]["hostIP"]

        # Build the url
        set_url = f"http://{ip}:{port}"
        html = await tools.requests_get(set_url)

        assert "Hello, world!\n" in html.content.decode()

    finally:
        await cleanup()


async def test_clusterip_service_endpoint(model):
    """Create k8s Deployment and ClusterIP service, send request to ClusterIP
    from each kubernetes master and worker
    """

    async def test_svc(unit, ip) -> bool:
        # Build the url
        url = f"http://{ip}:{SVC_PORT}"
        cmd = f'curl -vk --noproxy "{ip}" {url}'
        action = await juju_run(unit, cmd, check=False, timeout=10)
        success = action.success and "Hello, world!\n" in action.stdout
        if not success:
            err_message = f"Failed to curl {url} from {unit.name}"
            err_message += f"\n  Command: {cmd}"
            err_message += f"\n  Exit code: {action.code}"
            err_message += f"\n  Output: {action.stdout}"
            err_message += f"\n  Error: {action.stderr}"
            log.error(err_message)
        else:
            log.info("Successfully curled %s from %s", url, unit.name)
        return success

    try:
        await setup_svc("ClusterIP")

        # Grab ClusterIP from svc
        pod = get_svc_yaml()
        ip = pod["items"][0]["spec"]["clusterIP"]

        # curl the ClusterIP from each control-plane and worker unit
        control_plane = model.applications["kubernetes-control-plane"]
        worker = model.applications["kubernetes-worker"]
        nodes_lst = control_plane.units + worker.units
        reachable = await asyncio.gather(*[test_svc(unit, ip) for unit in nodes_lst])
        for unit, success in zip(nodes_lst, reachable):
            assert success, f"Failed to reach {ip} from {unit.name}"

    finally:
        await cleanup()
