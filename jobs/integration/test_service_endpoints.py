import sh
import requests
import yaml
from .utils import retry_async_with_timeout, juju_run


def get_pod_yaml():
    out = sh.kubectl.get("po", o="yaml", selector="app=hello-world")
    return yaml.safe_load(out.stdout.decode())


def get_svc_yaml():
    out = sh.kubectl.get("svc", o="yaml", selector="app=hello-world")
    return yaml.safe_load(out.stdout.decode())


async def is_pod_running():
    pod = get_pod_yaml()

    try:
        phase = pod["items"][0]["status"]["phase"]
    except IndexError:
        # Pod is not created yet
        return False

    if "Running" in phase:
        return True
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
    sh.kubectl.set("env", "deployment/hello-world", "PORT=50000")

    # Create Service
    sh.kubectl.expose(
        "deployment",
        "hello-world",
        type=f"{svc_type}",
        name="hello-world",
        protocol="TCP",
        port=80,
        target_port=50000,
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


async def test_nodeport_service_endpoint():
    """Create k8s Deployement and NodePort service, send request to NodePort"""

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
        html = await requests.get(set_url)

        assert "Hello, world!\n" in html.content.decode()

    finally:
        await cleanup()


async def test_clusterip_service_endpoint(model):
    """Create k8s Deployement and ClusterIP service, send request to ClusterIP
    from each kubernetes master and worker
    """

    try:
        await setup_svc("ClusterIP")

        # Grab ClusterIP from svc
        pod = get_svc_yaml()
        ip = pod["items"][0]["spec"]["clusterIP"]

        # Build the url
        set_url = f"http://{ip}:80"
        cmd = f'curl -vk --noproxy "{ip}" {set_url}'

        # Curl the ClusterIP from each control-plane and worker unit
        control_plane = model.applications["kubernetes-control-plane"]
        worker = model.applications["kubernetes-worker"]
        nodes_lst = control_plane.units + worker.units
        for unit in nodes_lst:
            action = await juju_run(unit, cmd)
            assert "Hello, world!\n" in action.stdout

    finally:
        await cleanup()
