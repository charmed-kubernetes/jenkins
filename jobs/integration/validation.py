import asyncio
import base64
from dataclasses import dataclass
from typing import Callable, Mapping

import backoff
import ipaddress
import json
import os
import requests
import yaml
import random
import pytest
import logging
import click
import jinja2
from base64 import b64encode

from datetime import datetime
from pathlib import Path
from pprint import pformat
from tempfile import NamedTemporaryFile
from types import SimpleNamespace
from .utils import (
    juju_run_retry,
    timeout_for_current_task,
    retry_async_with_timeout,
    scp_to,
    disable_source_dest_check,
    find_entities,
    verify_deleted,
    verify_ready,
    is_localhost,
    validate_storage_class,
    SERIES_ORDER,
    refresh_openstack_charms,
    prep_series_upgrade,
    do_series_upgrade,
    finish_series_upgrade,
    kubectl,
    kubectl_apply,
    kubectl_delete,
    render,
    render_and_apply,
    render_and_delete,
    juju_run,
    juju_run_action,
    machine_reboot,
    get_ipv6_addr,
    vault,
    vault_status,
    get_svc_ingress,
)
import urllib.request
from bs4 import BeautifulSoup as bs
from bs4.element import ResultSet as bs_ResultSet
from juju.application import Application
from juju.unit import Unit

# Quiet the noise
logging.getLogger("asyncio").setLevel(logging.INFO)
logging.getLogger("connector").setLevel(logging.INFO)
logging.getLogger("websockets.client").setLevel(logging.INFO)
logging.getLogger("websockets.protocol").setLevel(logging.INFO)
# bump up juju debug
logging.getLogger("juju").setLevel(logging.INFO)
# validation logging
log = logging.getLogger(__name__)


class MicrobotError(Exception):
    pass


class AuditTimestampError(Exception):
    pass


async def wait_for_process(model, arg):
    """Retry api_server_with_arg <checks> times with a 5 sec interval"""
    checks = 60
    ready = False
    while not ready:
        checks -= 1
        if await api_server_with_arg(model, arg):
            return
        else:
            if checks <= 0:
                assert False
            await asyncio.sleep(5)


async def wait_for_not_process(model, arg):
    """Retry api_server_with_arg <checks> times with a 5 sec interval"""
    checks = 60
    ready = False
    while not ready:
        checks -= 1
        if await api_server_with_arg(model, arg):
            if checks <= 0:
                assert False
            await asyncio.sleep(5)
        else:
            return


async def api_server_with_arg(model, argument):
    control_plane = model.applications["kubernetes-control-plane"]
    for unit in control_plane.units:
        search = "ps -ef | grep {} | grep apiserver".format(argument)
        action = await juju_run(unit, search, check=False)
        assert action.status == "completed"
        raw_output = action.stdout or ""
        if len(raw_output.splitlines()) != 1:
            return False
    return True


async def run_until_success(unit, cmd, timeout_insec=None):
    action = await juju_run_retry(unit, cmd, tries=float("inf"), timeout=timeout_insec)
    return action.stdout


async def run_and_check(desc, unit, cmd, timeout=None):
    result = await juju_run(unit, cmd, timeout=timeout)
    assert (result.status, result.code) == ("completed", 0), (
        f"Failed to {desc}:\n"
        f"  status={result.status}\n"
        f"  code={result.code}\n"
        f"  stdout={result.stdout}\n"
        f"  stderr={result.stderr}"
    )
    return result.stdout


async def get_last_audit_entry_date(application):
    times = []
    for unit in application.units:
        while True:
            cmd = "cat /root/cdk/audit/audit.log | tail -n 1"
            raw = await run_until_success(unit, cmd)
            try:
                data = json.loads(raw)
                break
            except json.JSONDecodeError:
                print("Failed to read audit log entry: " + raw)
        if "timestamp" in data:
            timestamp = data["timestamp"]
            time = datetime.strptime(timestamp, "%Y-%m-%dT%H:%M:%SZ")
        elif "requestReceivedTimestamp" in data:
            timestamp = data["requestReceivedTimestamp"]
            time = datetime.strptime(timestamp, "%Y-%m-%dT%H:%M:%S.%fZ")
        else:
            raise AuditTimestampError("Unable to find timestamp in {}".format(data))
        times.append(time)
    return sorted(times)[-1]


async def set_config_and_wait(app: Application, config, tools, max_wait=False):
    log.debug("Getting config for %s", app.name)
    current_config = await app.get_config()

    if all(config[key] == current_config[key]["value"] for key in config):
        log.info("set_config_and_wait: new config identical to current, skipping")
        return

    log.debug("Setting configs for %s (%s)", app.name, ",".join(config.keys()))
    await app.set_config(config)
    await tools.juju_wait(max_wait=max_wait)


async def reset_audit_config(control_plane_app, tools):
    audit_configs = ["audit-policy", "audit-webhook-config", "api-extra-args"]
    log.debug("Resetting audit configs")
    config = await control_plane_app.get_config()
    defaults = {k: config[k]["default"] for k in audit_configs}
    await set_config_and_wait(control_plane_app, defaults, tools)


# START TESTS
@pytest.mark.skip("Feature removed in ops rewrite")
async def test_auth_file_propagation(model, tools):
    """Validate that changes to /root/cdk/serviceaccount.key on the leader
    control-plane unit are propagated to the other control-plane units.

    """
    # Get a leader and non-leader unit to test with
    masters = model.applications["kubernetes-control-plane"]
    if len(masters.units) < 2:
        pytest.skip("Test requires multiple control-plane units")

    for master in masters.units:
        if await master.is_leader_from_status():
            leader = master
        else:
            follower = master

    # Change serviceaccount.key on the leader, and get its md5sum
    leader_md5 = await run_until_success(
        leader,
        "echo '#EXTRA' >> /root/cdk/serviceaccount.key && "
        "md5sum /root/cdk/serviceaccount.key",
    )

    # fail the test if we're waiting more than 10 minutes
    max_wait = 10 * 60

    # Check that md5sum on non-leader matches
    follower_md5 = await run_until_success(
        follower,
        'md5sum /root/cdk/serviceaccount.key | grep "{}"'.format(leader_md5),
        timeout_insec=max_wait,
    )

    try:
        assert follower_md5 == leader_md5, "Units didn't match"
    finally:
        # Cleanup (remove the line we added)
        await run_until_success(leader, "sed -i '$d' /root/cdk/serviceaccount.key")
        await tools.juju_wait(max_wait=max_wait)


@pytest.mark.flaky(max_runs=5, min_passes=1)
async def test_status_messages(model):
    """Validate that the status messages are correct."""
    expected_messages = {
        "kubernetes-control-plane": "",
        "kubernetes-worker": "",
    }
    for app, message in expected_messages.items():
        for unit in model.applications[app].units:
            assert message in unit.workload_status_message


async def test_snap_versions(model, tools):
    """Validate that the installed snap versions are consistent with channel
    config on the charms.
    """
    snaps_to_validate = {
        "kubernetes-control-plane": [
            "kubectl",
            "kube-apiserver",
            "kube-controller-manager",
            "kube-scheduler",
            "cdk-addons",
        ],
        "kubernetes-worker": ["kubectl", "kubelet", "kube-proxy"],
    }

    for app_name, snaps in snaps_to_validate.items():
        app = model.applications[app_name]
        config = await app.get_config()
        channel = config["channel"]["value"]
        if "/" not in channel:
            message = "validate_snap_versions: skipping %s, channel=%s"
            message = message % (app_name, channel)
            click.echo(message)
            continue
        track, risk = channel.split("/", 1)
        if track == "latest":
            # Use snap info to determine the versions of the latest/{risk}
            stdout, *_ = await tools.run("snap", "info", *snaps)
            info = {
                i["name"]: i["channels"][channel].split(".", 2)[:2]
                for i in yaml.safe_load_all(stdout)
            }
            expected, *_ = info.values()
            track = ".".join(expected)
            err = f"not all {channel} snaps are on an the same track={track}"
            assert all(i == expected for i in info.values()), err
        for unit in app.units:
            action = await juju_run(unit, "snap list", check=False)
            assert action.status == "completed"
            # Example of the `snap list` output format we're expecting:
            # Name        Version  Rev   Developer  Notes
            # conjure-up  2.1.5    352   canonical  classic
            # core        16-2     1689  canonical  -
            # kubectl     1.6.2    27    canonical  classic
            lines = action.stdout.splitlines()[1:]
            snap_versions = dict(line.split()[:2] for line in lines)
            for snap in snaps:
                snap_version = snap_versions[snap]
                if snap == "cdk-addons":
                    # cdk-addons is a special case, it may have a charm_branch file which defines the snap track
                    charm_branch = await juju_run(
                        unit, "tail -n1 templates/charm_branch", check=False
                    )
                    if not charm_branch.success:
                        # follows the same track as the other snaps
                        addons_track = track
                        log.info(
                            "cdk-addons track not defined, following %s", addons_track
                        )
                    elif (branch := charm_branch.stdout.strip()).startswith("release_"):
                        # follows the track defined in the charm_branch file
                        addons_track = branch.replace("release_", "")
                        log.info(
                            "cdk-addons track defined by charm_branch: %s", addons_track
                        )
                    else:
                        # cdk-addons follows the track by latest/$risk in other cases.
                        stdout, *_ = await tools.run("snap", "info", snap)
                        snap_info = yaml.safe_load(stdout)
                        if version := snap_info.get("channels", {}).get(
                            f"latest/{risk}"
                        ):
                            addons_track = ".".join(version.split(".", 2)[:2])
                            log.info(
                                "cdk-addons track defined by latest/%s: %s",
                                risk,
                                addons_track,
                            )
                        else:
                            raise ValueError(
                                f"no latest/{risk} version found for cdk-addons"
                            )
                    msg = f"{unit.name}: Snap {snap} is version {snap_version} and not {addons_track}.*"
                    assert snap_version.startswith(addons_track + "."), msg
                else:
                    msg = f"{unit.name}: Snap {snap} is version {snap_version} and not {track}.*"
                    assert snap_version.startswith(track + "."), msg


async def test_rbac(model):
    """When RBAC is enabled, validate kubelet creds cannot get ClusterRoles"""
    app = model.applications["kubernetes-control-plane"]
    config = await app.get_config()
    if "RBAC" not in config["authorization-mode"]["value"]:
        pytest.skip("Cluster does not have RBAC enabled")

    cmd = "/snap/bin/kubectl --kubeconfig /root/cdk/kubeconfig get clusterroles"
    worker = model.applications["kubernetes-worker"].units[0]
    await run_until_success(worker, cmd + " 2>&1 | grep Forbidden")


@pytest.fixture
def microbot_deployment(model, tmp_path):
    parent = Path(__file__).parent
    path_to_deployment = parent / "templates" / "microbot.yaml"
    kw = model.applications["kubernetes-worker"]
    machine = kw.units[0].machine
    machine_arch = machine.safe_data["hardware-characteristics"]["arch"]

    context = {
        "arch": machine_arch,
        "public_address": kw.units[0].public_address,
        "replicas": len(kw.units),
        "registry": "rocks.canonical.com:443/cdk",
    }
    content = jinja2.Template(path_to_deployment.read_text()).render(context)
    path = tmp_path / "microbot.yaml"
    path.write_text(content)
    yield path


@pytest.fixture
async def teardown_microbot(model, microbot_deployment):
    await kubectl_delete(
        microbot_deployment, model, namespace="default", grace_period=5 * 60
    )


@pytest.fixture
async def setup_microbot(model, microbot_deployment):
    """Setup the microbot on ingress"""
    await kubectl_apply(microbot_deployment, model, namespace="default")
    unit = model.applications["kubernetes-worker"].units[0]
    await retry_async_with_timeout(
        verify_ready,
        (unit, "po", ["microbot"], "-n default"),
        timeout_msg="Unable to create microbot pods for test",
    )
    yield "http://microbot.{public_address}.nip.io"
    await kubectl_delete(
        microbot_deployment, model, namespace="default", grace_period=5 * 60
    )


@pytest.mark.clouds(["azure", "ec2", "vsphere"])
async def test_microbot(model, tools, setup_microbot):
    """Validate the microbot action"""
    kw = model.applications["kubernetes-worker"].units[0]
    url = setup_microbot.format(public_address=kw.public_address)
    _times, _sleep = 5, 60
    for _ in range(_times):  # 5 min should be enough time
        try:
            resp = await tools.requests_get(
                url,
                proxies={"http": None, "https": None},
            )
            if resp.status_code == 200:
                break
        except requests.exceptions.ConnectionError as e:
            click.echo(
                f"Caught connection error attempting to hit {url}, "
                f"retrying. Error follows: {e}"
            )
        await asyncio.sleep(_sleep)
    else:
        pytest.fail(f"Failed to connect to microbot after {_times * _sleep} sec")


@pytest.mark.clouds(["azure", "ec2", "vsphere"])
@pytest.mark.usefixtures("log_dir")
@backoff.on_exception(backoff.expo, TypeError, max_tries=5)
async def test_dashboard(model, kubeconfig, tools):
    """Validate that the dashboard is operational"""
    unit = model.applications["kubernetes-control-plane"].units[0]
    config = yaml.safe_load(kubeconfig.open())

    async def query_dashboard(url, config):
        # handle pre 1.19 authentication
        try:
            user = config["users"][0]["user"]["username"]
            password = config["users"][0]["user"]["password"]
            auth = tools.requests.auth.HTTPBasicAuth(user, password)
            resp = await tools.requests_get(url, auth=auth, verify=False)
        except KeyError:
            token = config["users"][0]["user"]["token"]
            headers = {"Authorization": f"Bearer {token}"}
            resp = await tools.requests_get(url, headers=headers, verify=False)
        return resp

    # make sure we can hit the api-server
    url = config["clusters"][0]["cluster"]["server"]

    can_access_dashboard = await query_dashboard(url, config)
    assert can_access_dashboard.status_code == 200

    dash_ns = "kubernetes-dashboard"
    # construct the url to the dashboard login form
    url = (
        f"{url}/api/v1/namespaces/{dash_ns}/services/https:kubernetes-dashboard:"
        "/proxy/#!/login"
    )

    click.echo("Waiting for dashboard to stabilize...")

    async def dashboard_present(url, config):
        resp = await query_dashboard(url, config)
        if resp.status_code == 200 and "Dashboard" in resp.text:
            return True
        return False

    await retry_async_with_timeout(
        verify_ready,
        (unit, "po", ["kubernetes-dashboard"], f"-n {dash_ns}"),
        timeout_msg="Unable to find kubernetes dashboard before timeout",
    )

    await retry_async_with_timeout(
        dashboard_present, (url, config), timeout_msg="Unable to reach dashboard"
    )


async def test_kubelet_anonymous_auth_disabled(model, tools):
    """Validate that kubelet has anonymous auth disabled"""

    async def validate_unit(unit):
        await juju_run(unit, "open-port 10250")
        address = unit.public_address
        url = "https://%s:10250/pods/" % address
        for attempt in range(0, 120):  # 2 minutes
            try:
                response = await tools.requests_get(
                    url, verify=False, proxies={"http": None, "https": None}
                )
                assert response.status_code == 401  # Unauthorized
                break
            except requests.exceptions.ConnectionError:
                log.info(
                    "Failed to connect to kubelet on {}; retrying in 10s".format(
                        unit.name
                    )
                )
                await asyncio.sleep(10)
        else:
            output = await juju_run(
                unit, "systemctl status --no-pager snap.kubelet.daemon", check=False
            )
            if "active (running)" not in output.stdout:
                raise AssertionError(
                    "kubelet not running on {}: {}".format(
                        unit.name, output.stdout or output.stderr
                    )
                )
            else:
                await juju_run(
                    unit, "which netstat || apt install net-tools", check=False
                )
                output = await juju_run(unit, "netstat -tnlp", check=False)
                raise AssertionError(
                    "Unable to connect to kubelet on {}: {}".format(
                        unit.name,
                        output.stdout or output.stderr,
                    )
                )

    units = model.applications["kubernetes-worker"].units
    await asyncio.gather(*(validate_unit(unit) for unit in units))


@pytest.mark.skip_if_apps(
    # skip this test if none of these CNIs is deployed
    lambda apps: not any(a in apps for a in ["canal", "calico", "tigera-secure-ee"])
)
async def test_network_policies(model, tools):
    """Apply network policy and use two busyboxes to validate it."""
    here = os.path.dirname(os.path.abspath(__file__))
    unit = model.applications["kubernetes-control-plane"].units[0]

    # Clean-up namespace from any previous runs.
    await juju_run(
        unit,
        "/snap/bin/kubectl --kubeconfig /root/.kube/config delete ns netpolicy",
        check=False,
    )
    click.echo("Waiting for pods to finish terminating...")

    await retry_async_with_timeout(
        verify_deleted,
        (unit, "ns", ["netpolicy"]),
        timeout_msg="Unable to remove the namespace netpolicy",
    )

    # Move manifests to the master
    await scp_to(
        os.path.join(here, "templates", "netpolicy-test.yaml"),
        unit,
        "netpolicy-test.yaml",
        tools.controller_name,
        tools.connection,
        proxy=tools.juju_ssh_proxy,
    )
    await scp_to(
        os.path.join(here, "templates", "restrict.yaml"),
        unit,
        "restrict.yaml",
        tools.controller_name,
        tools.connection,
        proxy=tools.juju_ssh_proxy,
    )
    cmd = await juju_run(
        unit,
        "/snap/bin/kubectl --kubeconfig /root/.kube/config create -f /home/ubuntu/netpolicy-test.yaml",
        check=False,
    )
    if not cmd.code == 0:
        click.echo("Failed to create netpolicy test!")
        click.echo(cmd.results)
    assert cmd.status == "completed" and cmd.code == 0
    click.echo("Waiting for pods to show up...")
    await retry_async_with_timeout(
        verify_ready,
        (unit, "po", ["bboxgood", "bboxbad"], "-n netpolicy"),
        timeout_msg="Unable to create pods for network policy test",
    )

    # Try to get to nginx from both busyboxes.
    # We expect no failures since we have not applied the policy yet.
    async def get_to_networkpolicy_service():
        click.echo("Reaching out to nginx.netpolicy with no restrictions")
        query_from_bad = "/snap/bin/kubectl --kubeconfig /root/.kube/config exec bboxbad -n netpolicy -- wget --timeout=30  nginx.netpolicy"
        query_from_good = "/snap/bin/kubectl --kubeconfig /root/.kube/config exec bboxgood -n netpolicy -- wget --timeout=30  nginx.netpolicy"
        cmd_good = await juju_run(unit, query_from_good, check=False)
        cmd_bad = await juju_run(unit, query_from_bad, check=False)
        if (
            cmd_good.status == "completed"
            and cmd_bad.status == "completed"
            and "index.html" in cmd_good.stderr
            and "index.html" in cmd_bad.stderr
        ):
            return True
        log.warning("No restrictions: bboxdbad: (%s)", cmd_bad.results)
        log.warning("No restrictions: bboxgood: (%s)", cmd_good.results)
        return False

    await retry_async_with_timeout(
        get_to_networkpolicy_service,
        (),
        timeout_msg="Failed to query nginx.netpolicy even before applying restrictions",
    )

    # Apply network policy and retry getting to nginx.
    # This time the policy should block us.
    cmd = await juju_run(
        unit,
        "/snap/bin/kubectl --kubeconfig /root/.kube/config create -f /home/ubuntu/restrict.yaml",
        check=False,
    )
    assert cmd.status == "completed"
    await asyncio.sleep(10)

    async def get_to_restricted_networkpolicy_service():
        click.echo("Reaching out to nginx.netpolicy with restrictions")
        query_from_bad = (
            "/snap/bin/kubectl --kubeconfig /root/.kube/config exec bboxbad -n netpolicy -- "
            "wget --timeout=30  nginx.netpolicy -O foo.html"
        )
        query_from_good = (
            "/snap/bin/kubectl --kubeconfig /root/.kube/config exec bboxgood -n netpolicy -- "
            "wget --timeout=30  nginx.netpolicy -O foo.html"
        )
        cmd_good = await juju_run(unit, query_from_good, check=False)
        cmd_bad = await juju_run(unit, query_from_bad, check=False)
        if (
            cmd_good.status == "completed"
            and cmd_bad.status == "completed"
            and "foo.html" in cmd_good.stderr
            and "timed out" in cmd_bad.stderr
        ):
            return True
        log.warning("Restricted: bboxdbad: (%s)", cmd_bad.results)
        log.warning("Restricted: bboxgood: (%s)", cmd_good.results)
        return False

    await retry_async_with_timeout(
        get_to_restricted_networkpolicy_service,
        (),
        timeout_msg="Failed query restricted nginx.netpolicy",
    )

    # Clean-up namespace from next runs.
    cmd = await juju_run(
        unit, "/snap/bin/kubectl --kubeconfig /root/.kube/config delete ns netpolicy"
    )
    assert cmd.status == "completed"


async def test_ipv6(model, tools):
    control_plane_app = model.applications["kubernetes-control-plane"]
    master_config = await control_plane_app.get_config()
    service_cidr = master_config["service-cidr"]["value"]
    if all(ipaddress.ip_network(cidr).version != 6 for cidr in service_cidr.split(",")):
        pytest.skip("kubernetes-control-plane not configured for IPv6")

    control_plane = control_plane_app.units[0]
    await kubectl(
        model,
        "apply -f - << EOF{}EOF".format(
            """
apiVersion: apps/v1
kind: Deployment
metadata:
  name: nginxdualstack
spec:
  selector:
    matchLabels:
      run: nginxdualstack
  replicas: 2
  template:
    metadata:
      labels:
        run: nginxdualstack
    spec:
      containers:
      - name: nginxdualstack
        image: rocks.canonical.com/cdk/diverdane/nginxdualstack:1.0.0
        ports:
        - containerPort: 80
---
apiVersion: v1
kind: Service
metadata:
  name: nginx6
  labels:
    run: nginxdualstack
spec:
  type: NodePort
  ipFamilies: [IPv6]
  ports:
  - port: 80
    protocol: TCP
  selector:
    run: nginxdualstack
---
apiVersion: v1
kind: Service
metadata:
  name: nginx4
  labels:
    run: nginxdualstack
spec:
  type: NodePort
  ipFamilies: [IPv4]
  ports:
  - port: 80
    protocol: TCP
  selector:
    run: nginxdualstack
"""
        ),
    )

    # wait for completion
    await retry_async_with_timeout(
        verify_ready,
        (control_plane, "svc", ["nginx4", "nginx6"]),
        timeout_msg="Timeout waiting for nginxdualstack services",
    )
    nginx4, nginx6 = await find_entities(control_plane, "svc", ["nginx4", "nginx6"])
    ipv4_port = nginx4["spec"]["ports"][0]["nodePort"]
    ipv6_port = nginx6["spec"]["ports"][0]["nodePort"]
    urls = []
    for worker in model.applications["kubernetes-worker"].units:
        for port in (ipv4_port, ipv6_port):
            await juju_run(worker, "open-port {}".format(port))
        ipv4_addr = worker.public_address
        ipv6_addr = await get_ipv6_addr(worker)
        assert ipv6_addr is not None, "Unable to find IPv6 address for {}".format(
            worker.name
        )
        urls.extend(
            [
                "http://{}:{}/".format(ipv4_addr, ipv4_port),
                "http://[{}]:{}/".format(ipv6_addr, ipv6_port),
            ]
        )
    for url in urls:
        # pods might not be up by this point, retry until it works
        with timeout_for_current_task(60):
            while True:
                cmd = "curl '{}' --max-time 1".format(url)
                output = await juju_run(control_plane, cmd, check=False)
                if (
                    output.status == "completed"
                    and output.code == 0
                    and "Kubernetes IPv6 nginx" in output.stdout
                ):
                    break
                await asyncio.sleep(1)


@pytest.mark.skip("Unskip when this can be speed up considerably")
async def test_worker_master_removal(model, tools):
    # Add a second master
    masters = model.applications["kubernetes-control-plane"]
    original_master_count = len(masters.units)
    if original_master_count < 2:
        await masters.add_unit(1)
        await disable_source_dest_check(tools.model_name)

    # Add a second worker
    workers = model.applications["kubernetes-worker"]
    original_worker_count = len(workers.units)
    if original_worker_count < 2:
        await workers.add_unit(1)
        await disable_source_dest_check(tools.model_name)
    await tools.juju_wait()

    # Remove a worker to see how the masters handle it
    unit_count = len(workers.units)
    await workers.units[0].remove()
    await tools.juju_wait()

    while len(workers.units) == unit_count:
        await asyncio.sleep(15)
        click.echo(
            "Waiting for worker removal. (%d/%d)" % (len(workers.units), unit_count)
        )

    # Remove the master leader
    unit_count = len(masters.units)
    for master in masters.units:
        if await master.is_leader_from_status():
            await master.remove()
    await tools.juju_wait()

    while len(masters.units) == unit_count:
        await asyncio.sleep(15)
        click.echo(
            "Waiting for master removal. (%d/%d)" % (len(masters.units), unit_count)
        )

    # Try and restore the cluster state
    # Tests following this were passing, but they actually
    # would fail in a multi-control-plane situation
    while len(workers.units) < original_worker_count:
        await workers.add_unit(1)
    while len(masters.units) < original_master_count:
        await masters.add_unit(1)
    await disable_source_dest_check(tools.model_name)
    click.echo("Waiting for new master and worker.")
    await tools.juju_wait()


@pytest.mark.on_model("validate-nvidia")
async def test_gpu_support(model, k8s_model, tools):
    """Test gpu support. Should be disabled if hardware
    is not detected and functional if hardware is fine"""

    # Deploy nvidia-gpu-operator charm
    # Trust is True because the charm needs privileges to install drivers
    # and packages on the workers
    await k8s_model.deploy(
        entity_url="nvidia-gpu-operator", channel="latest/stable", trust=True
    )
    await k8s_model.wait_for_idle(status="active")
    # Find all nvidia based workers
    nvidia_workers = [
        unit
        for unit in model.applications["kubernetes-worker"].units
        if (await unit.machine.ssh("lspci -nnk")).lower().count("nvidia")
    ]

    control_plane = model.applications["kubernetes-control-plane"].units[0]
    verify_args = (
        control_plane,
        "ds",
        ["nvidia-device-plugin-daemonset"],
    )
    if not nvidia_workers:
        # nvidia should not be running
        await retry_async_with_timeout(
            verify_deleted,
            verify_args,
            timeout_msg="nvidia-device-plugin-daemonset is setup without nvidia hardware",
        )
        return

    # nvidia should be running
    try:
        await retry_async_with_timeout(
            verify_ready,
            verify_args,
            timeout_msg="nvidia-device-plugin-daemonset not running",
        )
    except asyncio.TimeoutError:
        log.exception("nvidia-device-plugin-daemonset is not running")
        log.info("restarting kubernetes-worker and retrying once more")
        for worker in nvidia_workers:
            await machine_reboot(worker.machine, block=True)
        await retry_async_with_timeout(
            verify_ready,
            verify_args,
            timeout_msg="nvidia-device-plugin-daemonset not running",
        )

    # Do an addition on the GPU just be sure.
    # First clean any previous runs
    local_path = Path(__file__).parent / "templates/nvidia-smi.yaml"
    await kubectl_delete(local_path, model, check=False)
    await retry_async_with_timeout(
        verify_deleted,
        (control_plane, "po", ["nvidia-smi"], "-n default"),
        timeout_msg="Cleaning of nvidia-smi pod failed",
    )
    # Run the cuda addition
    await kubectl_apply(local_path, model)

    async def cuda_test():
        nvidia_logs = await kubectl(model, "logs", "job.batch/nvidia-smi", check=False)
        log.info(nvidia_logs.stdout)
        return nvidia_logs.stdout.count("NVIDIA-SMI") > 0

    await retry_async_with_timeout(
        cuda_test,
        tuple(),
        timeout_msg="Cuda test did not pass",
        timeout_insec=20 * 60,
    )

    # Cleanup the deployed nvidia-gpu-operator charm
    k8s_model.remove_application("nvidia-gpu-operator")


async def test_extra_args(model, tools):
    async def get_filtered_service_args(app, service):
        results = []

        for unit in app.units:
            while True:
                action = await juju_run(unit, "pgrep -a " + service, check=False)
                assert action.status == "completed"
                pids = []

                if action.code == 0:
                    pids = [ps for ps in action.stdout.splitlines() if "snap" in ps]

                if len(pids) == 1:
                    arg_string = pids[0].split(" ", 2)[-1]
                    args = {arg.strip() for arg in arg_string.split("--")[1:]}
                    results.append(args)
                    break

                await asyncio.sleep(5)

        # charms sometimes choose the master randomly, filter out the master
        # arg so we can do comparisons reliably
        results = [
            {arg for arg in args if not arg.startswith("master=")} for args in results
        ]

        # implied true vs explicit true should be treated the same
        results = [
            {arg + "=true" if "=" not in arg else arg for arg in args}
            for args in results
        ]

        return results

    async def run_extra_args_test(app_name, new_config, expected_args):
        app = model.applications[app_name]
        original_config = await app.get_config()
        original_args = {}
        for service in expected_args:
            original_args[service] = await get_filtered_service_args(app, service)

        await app.set_config(new_config)
        await tools.juju_wait()

        with timeout_for_current_task(600):
            try:
                for service, expected_service_args in expected_args.items():
                    while True:
                        args_per_unit = await get_filtered_service_args(app, service)
                        if all(expected_service_args <= args for args in args_per_unit):
                            break
                        await asyncio.sleep(5)
            except asyncio.CancelledError as e:
                click.echo("Dumping locals:\n" + pformat(locals()))
                msg = f"While applying new_config to {app_name}, {service} has {args_per_unit}"
                raise AssertionError(msg) from e

        filtered_original_config = {
            key: original_config[key]["value"] for key in new_config
        }
        await app.set_config(filtered_original_config)
        await tools.juju_wait()

        with timeout_for_current_task(600):
            try:
                for service, original_service_args in original_args.items():
                    while True:
                        new_args = await get_filtered_service_args(app, service)
                        if new_args == original_service_args:
                            break
                        await asyncio.sleep(5)
            except asyncio.CancelledError as e:
                click.echo("Dumping locals:\n" + pformat(locals()))
                msg = f"While restoring config to {app_name}, {service} has {new_args}"
                raise AssertionError(msg) from e

    master_task = run_extra_args_test(
        app_name="kubernetes-control-plane",
        new_config={
            "api-extra-args": " ".join(
                [
                    "min-request-timeout=314",  # int arg, overrides a charm default
                    "watch-cache",  # bool arg, implied true
                    "profiling=false",  # bool arg, explicit false
                ]
            ),
            "controller-manager-extra-args": " ".join(
                [
                    "v=3",  # int arg, overrides a charm default
                    "profiling",  # bool arg, implied true
                    "contention-profiling=false",  # bool arg, explicit false
                ]
            ),
            "scheduler-extra-args": " ".join(
                [
                    "v=3",  # int arg, overrides a charm default
                    "profiling",  # bool arg, implied true
                    "contention-profiling=false",  # bool arg, explicit false
                ]
            ),
        },
        expected_args={
            "kube-apiserver": {
                "min-request-timeout=314",
                "watch-cache=true",
                "profiling=false",
            },
            "kube-controller": {"v=3", "profiling=true", "contention-profiling=false"},
            "kube-scheduler": {"v=3", "profiling=true", "contention-profiling=false"},
        },
    )

    worker_task = run_extra_args_test(
        app_name="kubernetes-worker",
        new_config={
            "kubelet-extra-args": " ".join(
                [
                    "v=1",  # int arg, overrides a charm default
                    "log-flush-frequency=5s",  # duration arg, explicitly 5s
                ]
            ),
            "proxy-extra-args": " ".join(
                [
                    "v=1",  # int arg, overrides a charm default
                    "profiling",  # bool arg, implied true
                    "log-flush-frequency=5s",  # duration arg, explicitly 5s
                ]
            ),
        },
        expected_args={
            "kubelet": {"v=1", "log-flush-frequency=5s"},
            "kube-proxy": {"v=1", "profiling=true", "log-flush-frequency=5s"},
        },
    )

    await asyncio.gather(master_task, worker_task)


async def test_kubelet_extra_config(model, tools):
    worker_app = model.applications["kubernetes-worker"]

    config = await worker_app.get_config()
    old_extra_config = config["kubelet-extra-config"]["value"]

    # set the new config
    new_extra_config = yaml.dump(
        {
            # maxPods, because it can be observed in the Node object
            "maxPods": 111,
            # evictionHard/memory.available, because it has a nested element
            "evictionHard": {"memory.available": "200Mi"},
            # authentication/webhook/enabled, so we can confirm that other
            # items in the authentication section are preserved
            "authentication": {"webhook": {"enabled": False}},
        }
    )
    try:
        await set_config_and_wait(
            worker_app, {"kubelet-extra-config": new_extra_config}, tools
        )

        # wait for and validate new maxPods value
        log.info("waiting for nodes to show new pod capacity")
        control_plane_unit = model.applications["kubernetes-control-plane"].units[0]
        for tries in range(19, -1, -1):  # 20 tries, 5s apart
            cmd = "/snap/bin/kubectl --kubeconfig /root/.kube/config -o yaml get node -l 'juju-application=kubernetes-worker'"
            action = await juju_run(control_plane_unit, cmd, check=False)
            if action.status == "completed" and action.code == 0:
                nodes = yaml.safe_load(action.stdout)
                s_nodes = ",".join(node["metadata"]["name"] for node in nodes["items"])
                w_nodes = ",".join(
                    node["metadata"]["name"]
                    for node in nodes["items"]
                    if node["status"]["capacity"]["pods"] != "111"
                )
                if not w_nodes:
                    log.info("All nodes(%s) adjusted capacity", s_nodes)
                    break
                log.warning("Waiting for nodes(%s) to adjust capacity", w_nodes)
            else:
                log.error("Failed to collect node status: %s", action.results)
            await asyncio.sleep(5)
            assert tries, "Timeout waiting for nodes to adjust capacity"

        # validate config.yaml on each worker
        log.info("validating generated config.yaml files")
        for worker_unit in worker_app.units:
            cmd = "cat /root/cdk/kubelet/config.yaml"
            action = await juju_run(worker_unit, cmd, check=False)
            if action.status == "completed" and action.code == 0:
                config = yaml.safe_load(action.stdout)
                assert config["evictionHard"]["memory.available"] == "200Mi"
                assert config["authentication"]["webhook"]["enabled"] is False
                assert "anonymous" in config["authentication"]
                assert "x509" in config["authentication"]
    finally:
        # clean up
        await set_config_and_wait(
            worker_app, {"kubelet-extra-config": old_extra_config}, tools
        )


@pytest.mark.skip("https://bugs.launchpad.net/bugs/2045696")
async def test_service_cidr_expansion(model, tools):
    """Expand the service cidr by 1 and verify if kubernetes service is
    updated with the new cluster IP.

    Note the cluster cannot revert back to the oiriginal service cidr.
    """
    app = model.applications["kubernetes-control-plane"]
    original_config = await app.get_config()
    original_service_cidr = original_config["service-cidr"]["value"]

    # Expand the service CIDR by 1
    new_service_networks = [
        ipaddress.ip_network(cidr).supernet()
        for cidr in original_service_cidr.split(",")
    ]
    new_service_cidr = ",".join(str(network) for network in new_service_networks)
    ips = new_service_networks[0].hosts()
    new_service_ip_str = str(next(ips))

    new_config = {"service-cidr": new_service_cidr}
    service_cluster_ip_range = "service-cluster-ip-range=" + str(new_service_cidr)
    await app.set_config(new_config)
    await wait_for_process(model, service_cluster_ip_range)

    output = await kubectl(model, "get service kubernetes")
    assert output.status == "completed"

    # Check if k8s service ip is changed as per new service cidr
    raw_output = output.stdout
    assert new_service_ip_str in raw_output

    # Wait for the model to be stable after 10 minutes
    async with tools.fast_forward(model, fast_interval="60s"):
        await model.wait_for_idle(status="active", timeout=10 * 60)


async def test_sans(model):
    example_domain = "santest.example.com"
    app = model.applications["kubernetes-control-plane"]
    original_config = await app.get_config()
    lb = None
    original_lb_config = None
    if "kubeapi-load-balancer" in model.applications:
        lb = model.applications["kubeapi-load-balancer"]
        original_lb_config = await lb.get_config()

    async def get_server_certs():
        results = {}
        for unit in app.units:
            action = await juju_run(
                unit,
                "openssl s_client -connect 127.0.0.1:6443 </dev/null 2>/dev/null | openssl x509 -text",
            )
            raw_output = action.stdout
            results[unit.name] = raw_output

        # if there is a load balancer, ask it as well
        if lb is not None:
            for unit in lb.units:
                action = await juju_run(
                    unit,
                    "openssl s_client -connect 127.0.0.1:443 </dev/null 2>/dev/null | openssl x509 -text",
                )
                raw_output = action.stdout
                results[unit.name] = raw_output

        return results

    async def all_certs_removed():
        certs = await get_server_certs()
        passing = True
        log.info("Checking for example domain removed from certs...")
        for unit_name, cert in certs.items():
            if example_domain in cert:
                passing = False
                log.info(f"Example domain still in cert for {unit_name}")
        return passing

    async def all_certs_in_place():
        certs = await get_server_certs()
        passing = True
        log.info("Checking for example domain added to certs...")
        for unit_name, cert in certs.items():
            if example_domain not in cert:
                passing = False
                if not cert:
                    log.info(f"Cert empty for {unit_name}")
                else:
                    log.info(f"Example domain not in cert for {unit_name}")
        return passing

    # add san to extra san list
    await app.set_config({"extra_sans": example_domain})
    if lb is not None:
        await lb.set_config({"extra_sans": example_domain})

    # wait for server certs to update
    await retry_async_with_timeout(
        all_certs_in_place,
        (),
        timeout_msg="extra sans config did not propagate to server certs",
    )

    # now remove it
    await app.set_config({"extra_sans": ""})
    if lb is not None:
        await lb.set_config({"extra_sans": ""})

    # verify it went away
    await retry_async_with_timeout(
        all_certs_removed,
        (),
        timeout_msg="extra sans config did not propagate to server certs",
    )

    # reset back to what they had before
    await app.set_config({"extra_sans": original_config["extra_sans"]["value"]})
    if lb is not None and original_lb_config is not None:
        await lb.set_config({"extra_sans": original_lb_config["extra_sans"]["value"]})


@pytest.mark.clouds(["ec2", "vsphere"])
async def test_toggle_metrics(model, tools):
    """Turn metrics on/off via the 'enable-metrics' config on kubernetes-control-plane,
    and check that workload status returns to 'active', and that the metrics-server
    svc is started and stopped appropriately.
    """

    async def check_svc(app, enabled):
        unit = app.units[0]
        if enabled:
            await retry_async_with_timeout(
                verify_ready,
                (unit, "svc", ["metrics-server"], "-n kube-system"),
                timeout_msg="Unable to find metrics-server svc before timeout",
            )
        else:
            await retry_async_with_timeout(
                verify_deleted,
                (unit, "svc", ["metrics-server"], "-n kube-system"),
                timeout_msg="metrics-server svc still exists after timeout",
            )

    app = model.applications["kubernetes-control-plane"]

    config = await app.get_config()
    old_value = config["enable-metrics"]["value"]
    new_value = not old_value

    await set_config_and_wait(
        app, {"enable-metrics": str(new_value)}, tools, max_wait=600
    )
    await check_svc(app, new_value)

    await set_config_and_wait(
        app, {"enable-metrics": str(old_value)}, tools, max_wait=600
    )
    await check_svc(app, old_value)


async def test_audit_empty_policy(model, tools):
    app = model.applications["kubernetes-control-plane"]

    # Set audit-policy to blank
    await reset_audit_config(app, tools)
    await set_config_and_wait(app, {"audit-policy": ""}, tools)

    try:
        # Verify no entries are being logged
        before_date = await get_last_audit_entry_date(app)
        await asyncio.sleep(5)
        await kubectl(model, "get po")
        after_date = await get_last_audit_entry_date(app)
        assert after_date == before_date

    finally:
        # Clean up
        log.info("Cleaning up test_audit_empty_policy")
        await reset_audit_config(app, tools)


async def test_audit_default_config(model, tools):
    app = model.applications["kubernetes-control-plane"]

    # Ensure we're using default configuration
    await reset_audit_config(app, tools)

    try:
        # Verify new entries are being logged
        unit = app.units[0]
        before_date = await get_last_audit_entry_date(app)
        await asyncio.sleep(5)
        await kubectl(model, "get po")
        after_date = await get_last_audit_entry_date(app)
        assert after_date > before_date

        # Verify total log size is less than 1 GB
        raw = await run_until_success(unit, "du -bs /root/cdk/audit")
        size_in_bytes = int(raw.split()[0])
        click.echo("Audit log size in bytes: %d" % size_in_bytes)
        max_size_in_bytes = 1000 * 1000 * 1000 * 1.01  # 1 GB, plus some tolerance
        assert size_in_bytes <= max_size_in_bytes
    finally:
        # Clean up
        await reset_audit_config(app, tools)


async def test_audit_custom_policy(model, tools):
    app = model.applications["kubernetes-control-plane"]

    # Set a custom policy that only logs requests to a special namespace
    namespace = "validate-audit-custom-policy"
    policy = {
        "apiVersion": "audit.k8s.io/v1",
        "kind": "Policy",
        "rules": [{"level": "Metadata", "namespaces": [namespace]}, {"level": "None"}],
    }
    await reset_audit_config(app, tools)
    await set_config_and_wait(app, {"audit-policy": yaml.dump(policy)}, tools)

    try:
        # Verify no entries are being logged
        before_date = await get_last_audit_entry_date(app)
        await asyncio.sleep(5)
        await kubectl(model, "get po")
        after_date = await get_last_audit_entry_date(app)
        assert after_date == before_date

        # Create our special namespace
        await kubectl(model, f"create ns {namespace}")

        # Verify our very special request gets logged
        before_date = await get_last_audit_entry_date(app)
        await asyncio.sleep(5)
        await kubectl(model, f"get po -n {namespace}")
        after_date = await get_last_audit_entry_date(app)
        assert after_date > before_date
    finally:
        # Clean up
        log.info("Cleaning up test_audit_custom_policy")
        await kubectl(model, f"delete ns {namespace}")
        await reset_audit_config(app, tools)


async def test_audit_webhook(model, tools):
    app = model.applications["kubernetes-control-plane"]
    unit = app.units[0]
    await reset_audit_config(app, tools)

    async def get_webhook_server_entry_count():
        result = await kubectl(model, "logs test-audit-webhook")
        lines = result.stdout.splitlines()
        return len(lines)

    # Deploy an nginx target for webhook
    local_path = Path(__file__).parent / "templates/test-audit-webhook.yaml"
    await kubectl_apply(local_path, model)

    await retry_async_with_timeout(
        verify_ready,
        (unit, "po", ["test-audit-webhook"], "-n default"),
        timeout_msg="Unable to find test-audit-webhook pod before timeout",
    )

    # Get test-audit-webhook pod IP
    test_ip = None
    while test_ip is None:
        result = await kubectl(model, "get po -o json test-audit-webhook")
        pod = json.loads(result.stdout)
        test_ip = pod["status"].get("podIP", None)

    # Set audit config with webhook enabled
    audit_webhook_config = {
        "apiVersion": "v1",
        "kind": "Config",
        "clusters": [
            {"name": "test-audit-webhook", "cluster": {"server": "http://" + test_ip}}
        ],
        "contexts": [
            {"name": "test-audit-webhook", "context": {"cluster": "test-audit-webhook"}}
        ],
        "current-context": "test-audit-webhook",
    }
    await set_config_and_wait(
        app,
        {
            "audit-webhook-config": yaml.dump(audit_webhook_config),
            "api-extra-args": "audit-webhook-mode=blocking",
        },
        tools,
    )

    try:
        # Ensure webhook log is growing
        before_count = await get_webhook_server_entry_count()
        await kubectl(model, "get po")
        after_count = await get_webhook_server_entry_count()
        assert after_count > before_count, "Audit Webhook isn't receiving audit logs"

    finally:
        # Clean up
        log.info("Cleaning up test_audit_webhook")
        await reset_audit_config(app, tools)
        await kubectl_delete(local_path, model)


@pytest.fixture()
async def any_keystone(model, apps_by_charm, tools):
    keystone_apps = apps_by_charm("keystone")

    if not (client := model.applications.get("keystone-client")):
        client = await model.deploy(
            "ubuntu",
            channel="stable",
            application_name="keystone-client",
            series=tools.series,
            num_units=1,
            config={},
        )

    if len(keystone_apps) > 1:
        pytest.fail(f"More than one keystone app available {','.join(keystone_apps)}")
    elif len(keystone_apps) == 1:
        # One keystone found
        keystone, *_ = keystone_apps.values()

        keystone_main = random.choice(keystone.units)
        action = await juju_run(keystone_main, "leader-get admin_passwd")
        admin_password = action.stdout.strip()

        yield SimpleNamespace(
            app=keystone, admin_password=admin_password, client=client.units[0]
        )
    else:
        # No keystone available, add/setup one
        admin_password = "testpw"
        channel, mysql_channel = "yoga/stable", "8.0/stable"
        keystone = await model.deploy(
            "keystone",
            channel=channel,
            series=tools.series,
            config={"admin-password": admin_password},
        )
        db_router = await model.deploy(
            "mysql-router",
            application_name="keystone-mysql-router",
            series=tools.series,
            channel=mysql_channel,
        )
        db = await model.deploy(
            "mysql-innodb-cluster",
            channel=mysql_channel,
            constraints="cores=2 mem=8G root-disk=64G",
            series=tools.series,
            num_units=3,
            config={
                "enable-binlogs": True,
                "innodb-buffer-pool-size": "256M",
                "max-connections": 2000,
                "wait-timeout": 3600,
            },
        )

        await model.integrate("keystone:shared-db", f"{db_router.name}:shared-db")
        await model.integrate(f"{db.name}:db-router", f"{db_router.name}:db-router")
        await tools.juju_wait()

        yield SimpleNamespace(
            app=keystone, admin_password=admin_password, client=client.units[0]
        )
        await tools.juju_wait()

        # cleanup
        await model.applications[keystone.name].destroy()
        await model.applications[db_router.name].destroy()
        await tools.juju_wait()
        db_name = db.name  # grab the db.name before its object dies
        await model.applications[db_name].destroy()
        await tools.juju_wait()

        # apparently, juju-wait will consider the model settled before an
        # application has fully gone away (presumably, when all units are gone) but
        # but having a dying mysql in the model can break the vault test

        try:
            await model.block_until(
                lambda: db_name not in model.applications, timeout=120
            )
        except asyncio.TimeoutError:
            pytest.fail(f"Timed out waiting for {db_name} to go away")


async def load_keystone_ca(model, apps_by_charm, keystone) -> str:
    def _find_relation(*specs):
        for rel in model.relations:
            if rel.matches(*specs):
                yield rel

    vault_root_ca = None
    vault_apps = apps_by_charm("vault")
    for name, vault_app in vault_apps.items():
        vault_tls = f"{name}:certificates"
        rels = set(
            app.name for rel in _find_relation(vault_tls) for app in rel.applications
        )
        if keystone.name in rels:
            vault_unit = random.choice(vault_app.units)
            action = await juju_run_action(vault_unit, "get-root-ca")
            vault_root_ca: str = action.results.get("output")
            if vault_root_ca:
                return base64.b64encode(vault_root_ca.encode()).decode()
    return ""


def cert_encode(cert: str) -> str:
    return base64.b64encode(cert.encode()).decode()


async def leader_read(unit: Unit, path: str):
    action = await juju_run(unit, f"cat {path}")
    return action.stdout


@pytest.fixture()
async def keystone_deployment(
    model, apps_by_charm, any_keystone, tools, tmp_path: Path
):
    keystone: Application = any_keystone.app
    control_plane: Application = model.applications["kubernetes-control-plane"]
    kubeapi_loadbalancer: Application = model.applications["kubeapi-load-balancer"]

    control_plane_unit = control_plane.units[0]
    server_crt = await leader_read(control_plane_unit, "/root/cdk/server.crt")
    server_key = await leader_read(control_plane_unit, "/root/cdk/server.key")
    await keystone.expose()

    # assemble key variables to populate the keystone deployment templates
    context = dict(
        # keystone endpoint data
        keystone_server_url=f"http://{keystone.units[0].public_address}:5000/v3",
        keystone_server_ca=await load_keystone_ca(model, apps_by_charm, keystone),
        # keystone auth endpoint data
        keystone_auth_crt=cert_encode(server_crt),
        keystone_auth_key=cert_encode(server_key),
        keystone_auth_service_ip="",  # filled in after service starts
        # keystone login data
        keystone_user="admin",
        keystone_password=any_keystone.admin_password,
        keystone_project="admin",
        keystone_domain="admin_domain",
        # kube api data
        kubernetes_api_server=f"https://{kubeapi_loadbalancer.units[0].public_address}",
    )
    # render and apply the keystone deployment templates
    resources = [
        "templates/keystone/keystone-deployment.yaml",
        "templates/keystone/keystone-policy-configmap.yaml",
        "templates/keystone/keystone-rbac.yaml",
        "templates/keystone/keystone-secret.yaml",
        "templates/keystone/keystone-service.yaml",
    ]

    await render_and_apply(*resources, context=context, model=model)

    # find the service ip of the keystone auth service
    svc_ip = ""
    while not svc_ip:
        auth_svc = await find_entities(
            control_plane_unit, "svc", ["k8s-keystone-auth-service"], "-n kube-system"
        )
        svc_ip = auth_svc[0]["spec"]["clusterIP"]
    context["keystone_auth_service_ip"] = svc_ip

    # setups the keystone-client with a kubeconfig
    original_config = await control_plane.get_config()
    kubeconfig = tmp_path / "config"
    kubeconfig.write_text(
        render("templates/keystone/keystone-kubeconfig.yaml", context=context)
    )
    await scp_to(
        kubeconfig,
        any_keystone.client,
        "/home/ubuntu/config",
        tools.controller_name,
        tools.connection,
        proxy=tools.juju_ssh_proxy,
    )
    await juju_run(
        any_keystone.client,
        (
            "snap install kubectl --classic;\n"
            "snap install client-keystone-auth;\n"
            "mkdir -p /root/.kube;\n"
            "mv /home/ubuntu/config /root/.kube/config;\n"
            "chown -R root:root /root/.kube;"
        ),
    )

    # configure the kube-apiserver to use the keystone auth webhook
    webhook_config = render(
        "templates/keystone/keystone-apiserver-webhook.yaml", context=context
    )
    await control_plane.set_config(
        {
            "authorization-webhook-config-file": webhook_config,
            "authorization-mode": "Node,Webhook,RBAC",
            "authn-webhook-endpoint": f"https://{svc_ip}:8443/webhook",
        }
    )
    await tools.juju_wait()
    yield any_keystone

    # cleanup
    await render_and_delete(*resources, context=context, model=model)
    await control_plane.set_config(original_config)
    await tools.juju_wait()


@pytest.mark.usefixtures("ceph_apps")
class TestCeph:
    async def test_plugins_installed(self, model):
        log.info("waiting for csi to settle")
        unit = model.applications["kubernetes-control-plane"].units[0]
        await retry_async_with_timeout(
            verify_ready,
            (unit, "po", ["csi-rbdplugin", "csi-cephfsplugin"], "-n kube-system"),
            timeout_msg="CSI pods not ready!",
        )

    @pytest.mark.parametrize(
        "storage_class",
        [
            "ceph-xfs",
            "ceph-ext4",
            "cephfs",
        ],
    )
    async def test_storage_class(self, model, log_open, storage_class):
        # create pod that writes to a pv from ceph
        kwds = dict(debug_open=log_open)
        kwds["provisioner"] = "csi-rbdplugin-provisioner"
        if storage_class == "cephfs":
            kwds["provisioner"] = "csi-cephfsplugin-provisioner"
        await validate_storage_class(model, storage_class, "Ceph", **kwds)


@pytest.mark.clouds(["ec2", "vsphere"])
async def test_keystone(model, keystone_deployment):
    control_plane = model.applications["kubernetes-control-plane"]
    control_plane_unit = random.choice(control_plane.units)

    # verify keystone pod is running
    await retry_async_with_timeout(
        verify_ready,
        (control_plane_unit, "po", ["k8s-keystone-auth"], "-n kube-system"),
        timeout_msg="Unable to find keystone auth pod before timeout",
    )

    # verify kube-apiserver configuration
    await wait_for_process(model, "authentication-token-webhook-config-file")
    await wait_for_process(model, "authorization-webhook-config-file")

    # verify auth fail - bad user
    kubectl = "kubectl --kubeconfig=/root/.kube/config"
    cmd = f"{kubectl} --context bad-user-context get clusterroles"
    output = await juju_run(keystone_deployment.client, cmd, check=False)
    assert output.status == "completed"
    assert "invalid user credentials" in output.stderr.lower(), output.stderr

    # verify auth fail - bad password
    cmd = f"{kubectl} --context bad-password-context get clusterroles"
    output = await juju_run(keystone_deployment.client, cmd, check=False)
    assert output.status == "completed"
    assert "invalid user credentials" in output.stderr.lower(), output.stderr

    # verify auth failure on pods outside of default namespace
    cmd = f"{kubectl} --context good-context get pod -n kube-system"
    output = await juju_run(keystone_deployment.client, cmd, check=False)
    assert output.status == "completed"
    assert 'cannot list resource "pods"' in output.stderr.lower(), output.stderr

    # verify auth success on pods
    cmd = f"{kubectl} --context good-context get pod"
    output = await juju_run(keystone_deployment.client, cmd, check=False)
    assert output.status == "completed"
    assert output.code == 0, output.stderr


@pytest.mark.on_model("validate-vault")
async def test_encryption_at_rest(model, tools):
    """Testing integrating vault secrets into cluster"""
    control_plane_app = model.applications["kubernetes-control-plane"]
    etcd_app = model.applications["etcd"]
    vault_app = model.applications["vault"]

    async def ensure_vault_up():
        await asyncio.gather(
            *(
                retry_async_with_timeout(vault_status, [unit])
                for unit in vault_app.units
            )
        )

    async def init_vault():
        # init vault
        click.echo("Initializing Vault")
        await ensure_vault_up()
        init_info = await vault(leader, "operator init -key-shares=5 -key-threshold=3")
        click.echo(init_info)
        # unseal vault leader (could also unseal follower, but it will be resealed later anyway)
        for key in init_info["unseal_keys_hex"][:3]:
            await vault(leader, "operator unseal " + key)

        # authorize charm
        click.echo("Authorizing charm")
        root_token = init_info["root_token"]
        token_info = await vault(
            leader, "token create -ttl=10m", VAULT_TOKEN=root_token
        )
        click.echo(token_info)
        charm_token = token_info["auth"]["client_token"]
        await juju_run_action(leader, "authorize-charm", token=charm_token)
        # At this point, Vault is up but in non-HA mode. If we weren't using the
        # auto-generate-root-ca-cert config, though, it would still be blocking
        # etcd until we ran either the generate-root-ca or upload-signed-csr
        # actions. NB: If we did need to manually generate or provide a root CA,
        # the current charm release (cs:vault-44) would also still be reporting the
        # less than helpful "'etcd' incomplete" status, while the newer charm would
        # more helpfully report that it was blocked on the root CA.

        # Since we are using the auto-generate-root-ca-cert config, though, we can
        # just go straight to waiting for etcd to settle.
        click.echo("Waiting for etcd to settle")
        await model.wait_for_idle(apps=["etcd"], timeout=30 * 60)
        for _ in range(3):
            actual_status = {unit.workload_status_message for unit in etcd_app.units}
            expected_status = {"Healthy with 3 known peers"}
            if actual_status == expected_status:
                break
            # The etcd service tends takes a bit to get the cluster up and
            # report the proper status, during which time it's not really
            # feasible for the charm code to block, so it sometimes takes an
            # update-status hook or two before the unit status is accurate. We
            # can hurry that along a bit, however.
            click.echo("Poking etcd to refresh status")
            await asyncio.gather(
                *(
                    juju_run(unit, "hooks/update-status", check=False)
                    for unit in etcd_app.units
                )
            )

        # Even once etcd is ready, Vault will remain in non-HA mode until the Vault
        # service is restarted, which will re-seal the vault.
        click.echo("Restarting Vault for HA")
        await asyncio.gather(
            *(
                juju_run(unit, "systemctl restart vault", check=False)
                for unit in vault_app.units
            )
        )
        await ensure_vault_up()

        click.echo("Unsealing Vault again in HA mode")
        for key in init_info["unseal_keys_hex"][:3]:
            await asyncio.gather(
                *(vault(unit, "operator unseal " + key) for unit in vault_app.units)
            )
        # force unit status to update
        await asyncio.gather(
            *(
                juju_run(unit, "hooks/update-status", check=False)
                for unit in vault_app.units
            )
        )
        assert await vault_ready_status()

    async def vault_ready_status():
        statuses = sorted(unit.workload_status_message for unit in vault_app.units)
        click.echo(statuses)
        return statuses == [
            "Unit is ready (active: false, mlock: disabled)",
            "Unit is ready (active: true, mlock: disabled)",
        ]

    click.echo("Waiting for Vault to settle")
    await model.wait_for_idle(apps=["vault"], timeout=30 * 60)

    if await vault_app.units[0].is_leader_from_status():
        leader = vault_app.units[0]
    else:
        leader = vault_app.units[1]

    if not await vault_ready_status():
        await init_vault()

    # NB: At this point, depending on the version of the Vault charm, its status
    # might either be (a less than informative) "'etcd' incomplete" (cs:vault-44)
    # or "Vault needs to be initialized" (cs:~openstack-charmers-next/vault).

    # Until https://github.com/juju-solutions/layer-vault-kv/pull/11 lands, the
    # k8s-control-plane units can go into error due to trying to talk to Vault during
    # the restart. Once Vault is back up, the errored hooks can just be retried.
    await model.wait_for_idle(
        apps=["kubernetes-control-plane"], raise_on_error=False, timeout=60 * 60
    )

    async def retry_hook(unit):
        # Until https://github.com/juju/python-libjuju/issues/484 is fixed, we
        # have to do this manually.
        from juju.client import client

        app_facade = client.ApplicationFacade.from_connection(unit.connection)
        await app_facade.ResolveUnitErrors(
            all_=False, retry=True, tags={"entities": [{"tag": unit.tag}]}
        )

    for _ in range(3):
        errored_units = [
            unit for unit in control_plane_app.units if unit.workload_status == "error"
        ]
        if not errored_units:
            break
        click.echo("Retrying failed k8s-control-plane hook for Vault restart")
        await asyncio.gather(*(retry_hook(unit) for unit in errored_units))
        await model.wait_for_idle(
            apps=["kubernetes-control-plane"], raise_on_error=False
        )

    # The cluster is probably mostly settled by this point, since the masters typically
    # take the longest to go into quiescence. However, in case they got into an errored
    # state, we need to give things another chance to settle out, while also checking
    # for any other failed units.
    click.echo("Waiting for cluster to settle")
    await model.wait_for_idle(status="active", raise_on_blocked=True, timeout=60 * 60)

    click.echo("Creating secret")
    await kubectl(
        model,
        "create secret generic test-secret --from-literal=username='secret-value'",
    )

    try:
        click.echo("Verifying secret")
        result = await kubectl(model, "get secret test-secret -o json")
        secret_value = json.loads(result.stdout)["data"]["username"]
        b64_value = b64encode(b"secret-value").decode("utf8")
        assert secret_value == b64_value

        click.echo("Verifying secret encryption")
        etcd = model.applications["etcd"].units[0]
        result = await juju_run(
            etcd,
            "ETCDCTL_API=3 /snap/bin/etcd.etcdctl "
            "--endpoints https://127.0.0.1:2379 "
            "--cacert=/var/snap/etcd/common/ca.crt "
            "--cert=/var/snap/etcd/common/server.crt "
            "--key=/var/snap/etcd/common/server.key "
            "get /registry/secrets/default/test-secret | strings",
        )
        assert "enc:aescbc:v1" in result.output, "Should see encoded secret"
        assert "secret-value" not in result.output, "Should not see plain-text secret"
    finally:
        click.echo("Deleting secret")
        await kubectl(model, "delete secret test-secret")


@pytest.mark.clouds(["ec2", "vsphere", "gce"])
async def test_dns_provider(model, k8s_model, tools):
    control_plane_app = model.applications["kubernetes-control-plane"]
    machine = control_plane_app.units[0].machine
    machine_arch = machine.safe_data["hardware-characteristics"]["arch"]

    async def deploy_validation_pod():
        async def _check_ready():
            log.info("Waiting for validation pod to start...")
            return (await kubectl(model, cmd, check=False)).success

        log.info("Deploying DNS pod")
        local_path = Path(__file__).parent / "templates/validate-dns-spec.yaml"
        await kubectl_apply(local_path, model)
        # wait for pod to be ready (having installed required packages), or failed
        cmd = "logs validate-dns | grep 'validate-dns: \\(Ready\\|Failed\\)'"
        await retry_async_with_timeout(_check_ready)

    async def remove_validation_pod():
        log.info("Removing DNS pod")
        await kubectl(model, "delete pod validate-dns --ignore-not-found")

    async def wait_for_pods_ready(label, ns="kube-system"):
        async def _check_ready():
            log.info("Waiting for validation pod to start...")
            result = await kubectl(model, cmd)
            return result.stdout and "false" not in result.stdout

        log.info(f"Waiting for pods with label {label} to be ready")
        cmd = f"get pod -n {ns} -l {label} -o jsonpath='{{.items[*].status.containerStatuses[*].started}}'"
        await retry_async_with_timeout(_check_ready)

    async def wait_for_pods_removal(label, ns="kube-system", force=False):
        async def _check_removed():
            result = await kubectl(model, cmd)
            if result.stdout == "":
                return True
            if force and ("true" not in result.stdout):
                log.info("All pods stuck in terminating, forcibly deleting them")
                kwds = {"grace-period": 0}
                await kubectl("delete", "pod", n=ns, l=label, force=True, **kwds)
                return True

        log.info(f"Waiting for pods with label {label} to be removed")
        cmd = f"get pod -n {ns} -l {label} -o jsonpath='{{.items[*].status.containerStatuses[*].started}}'"
        await retry_async_with_timeout(_check_removed)

    async def verify_dns_resolution(*, fresh):
        if fresh:
            await remove_validation_pod()
            await deploy_validation_pod()
        names = ["www.ubuntu.com", "kubernetes.default.svc.cluster.local"]
        for name in names:
            log.info(f"Checking domain {name}")
            response = await kubectl(
                model, f"exec validate-dns -- host {name}", check=False
            )
            assert response.success, f"Failed to resolve {name}"
            log.debug(response)

    async def verify_no_dns_resolution(**kwds):
        with pytest.raises(AssertionError, match=r"Failed to resolve"):
            await verify_dns_resolution(**kwds)

    async def get_offer():
        try:
            offers = await k8s_model.list_offers()
            for offer in offers.results:
                if offer.offer_name == "coredns":
                    return offer
            else:
                return None
        except TypeError:
            # work around https://github.com/juju/python-libjuju/pull/452
            return None

    try:
        await control_plane_app.set_config({"dns-provider": "auto"})
        await model.wait_for_idle(status="active")
        log.info("---")
        log.info("☆ Verifying DNS with default provider (auto -> coredns)")
        await verify_dns_resolution(fresh=True)

        await control_plane_app.set_config({"dns-provider": "none"})
        await model.wait_for_idle(status="active")
        log.info("---")
        log.info("☆ Verify no DNS with no provider (coredns -> none)")
        await wait_for_pods_removal("app.kubernetes.io/name=coredns")

        log.info("DNS shouldn't work on existing pod")
        await verify_no_dns_resolution(fresh=False)

        log.info("DNS shouldn't work on a fresh pod")
        await verify_no_dns_resolution(fresh=True)

        log.info("---")
        log.info("☆ Verifying DNS with CoreDNS charm")

        await k8s_model.deploy(
            f"ch:{machine_arch}/coredns",
            channel=tools.charm_channel,
            constraints={"arch": machine_arch},
            trust=True,
        )
        await k8s_model.block_until(lambda: "coredns" in k8s_model.applications)
        coredns = k8s_model.applications["coredns"]

        log.info("Waiting for CoreDNS charm to be ready")
        await k8s_model.wait_for_idle(raise_on_error=False, status="active")

        log.info("Creating cross-model offer")
        offer_name = f"{tools.k8s_model_name_full}.coredns"
        await k8s_model.create_offer("coredns:dns-provider")
        try:
            log.info("Waiting for cross-model offer to be ready")
            while not await get_offer():
                await asyncio.sleep(1)

            log.info("Consuming cross-model offer")
            await model.consume(offer_name, controller_name=tools.controller_name)

            log.info("Adding cross-model relation to CK")
            await model.add_relation("kubernetes-control-plane", "coredns")
            await k8s_model.wait_for_idle(status="active")
            await model.wait_for_idle(status="active")

            log.info("Waiting CoreDNS pod to be ready")
            await wait_for_pods_ready(
                "app.kubernetes.io/name=coredns", ns=tools.k8s_model_name
            )

            log.info("Verifying that stale pod doesn't pick up new DNS provider")
            await verify_no_dns_resolution(fresh=False)

            log.info("Verifying DNS works on fresh pod")
            await verify_dns_resolution(fresh=True)
        finally:
            log.info("Removing cross-model offer")
            if any("coredns" in rel.key for rel in control_plane_app.relations):
                await control_plane_app.destroy_relation("dns-provider", "coredns")
                await model.wait_for_idle(status="active")
            await model.remove_saas("coredns")
            await k8s_model.remove_offer(offer_name, force=True)
            log.info("Removing CoreDNS charm")
            await coredns.destroy(force=True)
            await wait_for_pods_removal(
                "app.kubernetes.io/name=coredns", ns=tools.k8s_model_name
            )

        log.info("---")
        log.info("☆ Verifying no DNS with no provider (removal of CoreDNS charm)")
        log.info("DNS shouldn't work on existing pod")
        await verify_no_dns_resolution(fresh=False)

        log.info("DNS shouldn't work on a fresh pod")
        await verify_no_dns_resolution(fresh=True)

        await control_plane_app.set_config({"dns-provider": "core-dns"})
        await model.wait_for_idle(status="active")
        log.info("---")
        log.info("☆ Verifying DNS with core-dns from cdk-addons (none -> coredns)")

        log.info("Waiting for CoreDNS pod to be ready")
        await wait_for_pods_ready("app.kubernetes.io/name=coredns")

        log.info("Verifying DNS works again")
        await verify_dns_resolution(fresh=True)
    finally:
        # Cleanup
        if (await control_plane_app.get_config())["dns-provider"] != "core-dns":
            await control_plane_app.set_config({"dns-provider": "core-dns"})
            await model.wait_for_idle(status="active")
        await remove_validation_pod()


async def test_sysctl(model, tools):
    if await is_localhost(tools.controller_name):
        pytest.skip("sysctl options not available on localhost")

    async def verify_sysctl(units, desired_values):
        cmd = "sysctl -n"
        desired_results = []
        for name, val in desired_values.items():
            cmd = cmd + " " + name
            desired_results.append(str(val))
        for unit in units:
            action = await juju_run(unit, cmd)
            raw_output = action.stdout
            lines = raw_output.splitlines()
            assert len(lines) == len(desired_results)
            if not lines == desired_results:
                click.echo(f"retry...{lines} != {desired_results}")
                return False
        return True

    test_values = [
        {
            "net.ipv4.neigh.default.gc_thresh1": 64,
            "net.ipv4.neigh.default.gc_thresh2": 128,
        },
        {
            "net.ipv4.neigh.default.gc_thresh1": 128,
            "net.ipv4.neigh.default.gc_thresh2": 256,
        },
    ]
    test_applications = [
        model.applications["kubernetes-control-plane"],
        model.applications["kubernetes-worker"],
    ]

    for app in test_applications:
        # save off config for restore later
        config = await app.get_config()

        for v in test_values:
            await app.set_config({"sysctl": str(v)})
            await retry_async_with_timeout(
                verify_sysctl,
                (app.units, v),
                timeout_msg="Unable to find sysctl changes before timeout",
            )

        await app.set_config({"sysctl": config["sysctl"]["value"]})


async def test_cloud_node_labels(cloud, model, tools):
    unit = model.applications["kubernetes-control-plane"].units[0]
    cmd = "/snap/bin/kubectl --kubeconfig /root/.kube/config get no -o json"
    raw_nodes = await run_until_success(unit, cmd)
    nodes = json.loads(raw_nodes)["items"]
    labels = [node["metadata"].get("labels", {}).get("juju.io/cloud") for node in nodes]
    all_same_labels = all(item == labels[0] for item in labels)
    assert (
        all_same_labels
    ), f"Unique label juju.io/cloud values found ({','.join(map(str, labels))})"

    label = labels[0]
    known_clouds = ["azure", "ec2", "gce", "openstack", "vsphere"]
    expected_label = f"Node label (juju.io/cloud={cloud})"
    if label is None:
        # if the label is None, expect there's no integrator app in the model
        integrators = [c + "-integrator" for c in known_clouds]
        integrator = set(app for app in integrators if app in model.applications)
        assert (
            not integrator
        ), f"Expect {expected_label} because the model is integrated with {integrator}"
    else:
        # Otherwise expect the label to match the cloud
        assert f"Node label (juju.io/cloud={label})" == expected_label


async def test_multus(model, tools, addons_model):
    if "multus" not in addons_model.applications:
        pytest.skip("multus is not deployed")

    unit = model.applications["kubernetes-control-plane"].units[0]
    multus_app = addons_model.applications["multus"]

    async def cleanup():
        await run_until_success(
            unit,
            "/snap/bin/kubectl --kubeconfig /root/.kube/config delete pod multus-test --ignore-not-found;"
            "/snap/bin/kubectl --kubeconfig /root/.kube/config delete subnet attachnet --ignore-not-found;",
        )
        await multus_app.reset_config(["network-attachment-definitions"])

    async def apply_def(content):
        remote_path = "/tmp/content.yaml"
        with NamedTemporaryFile("w") as f:
            yaml.dump(content, f)
            await scp_to(
                f.name,
                unit,
                remote_path,
                tools.controller_name,
                tools.connection,
                proxy=tools.juju_ssh_proxy,
            )
        await run_until_success(
            unit,
            f"/snap/bin/kubectl --kubeconfig /root/.kube/config apply -f {remote_path}; rm {remote_path}",
        )

    await cleanup()

    # Create NetworkAttachmentDefinition for KubeOVN
    net_attach_def = {
        "apiVersion": "k8s.cni.cncf.io/v1",
        "kind": "NetworkAttachmentDefinition",
        "metadata": {"name": "attachnet", "namespace": "default"},
        "spec": {
            "config": json.dumps(
                dict(
                    cniVersion="0.3.0",
                    type="kube-ovn",
                    server_socket="/run/openvswitch/kube-ovn-daemon.sock",
                    provider="attachnet.default.ovn",
                )
            )
        },
    }
    await multus_app.set_config(
        {"network-attachment-definitions": yaml.safe_dump(net_attach_def)}
    )

    # Create new subnet in OVN
    attachnet_def = dict(
        apiVersion="kubeovn.io/v1",
        kind="Subnet",
        metadata=dict(name="attachnet"),
        spec=dict(
            protocol="IPv4",
            cidrBlock="10.166.0.0/16",
            default=False,
            excludeIps=["10.166.0.1"],
            gateway="10.166.0.1",
            gatewayType="distributed",
            natOutgoing=True,
            namespaces=["default"],
        ),
    )

    # Create pod with 1 extra attachnet interface
    pod_definition = {
        "apiVersion": "v1",
        "kind": "Pod",
        "metadata": {
            "name": "multus-test",
            "annotations": {"k8s.v1.cni.cncf.io/networks": "default/attachnet"},
        },
        "spec": {
            "containers": [
                {
                    "name": "alpine",
                    "image": "rocks.canonical.com/alpine:latest",
                    "command": [
                        "/bin/ash",
                        "-c",
                        "trap : TERM INT; sleep 3600 & wait",
                    ],
                }
            ]
        },
    }
    await apply_def(attachnet_def)
    await apply_def(pod_definition)

    # Verify pod has the expected interfaces
    output = await run_until_success(
        unit,
        "/snap/bin/kubectl --kubeconfig /root/.kube/config exec multus-test -- ip a",
    )
    # behold, ugly output parsing :(
    try:
        lines = output.splitlines()
        active_networks = dict()
        while lines:
            line = lines.pop(0)
            interface = line.split()[1].rstrip(":").split("@")[0]
            while lines and lines[0].startswith(" "):
                line = lines.pop(0).strip()
                if line.startswith("inet "):
                    # interface has an address, we'll call that good enough
                    active_networks[interface] = line.split()[1]
        expected_interfaces = ["eth0", "net1"]
        for ifc in expected_interfaces:
            assert (
                ifc in active_networks
            ), f"Interface {ifc} is missing from ip addr output:\n{output}"
            assert active_networks[ifc].startswith(
                "10.166."
            ), f"Interface {ifc} is on the wrong subnet\n{output}"
    finally:
        await cleanup()


@dataclass
class NagiosAlerts:
    alerts: Mapping[str, bs_ResultSet]
    matchers: Mapping[str, Callable[[dict], bool]]

    def __bool__(self):
        """Successful if there are some alerts and all the matchers are True."""
        if not self.alerts:
            return False
        return all(
            self.matchers[severity](alerts) for severity, alerts in self.alerts.items()
        )

    def __getitem__(self, item: str) -> bs_ResultSet:
        return self.alerts[item]

    def __str__(self) -> str:
        return ", ".join(
            f"{severity}/{link.string}"
            for severity, alerts in self.alerts.items()
            for alert in alerts
            for link in alert.find_all("a", recursive=False)
        )


@dataclass
class NagiosApi:
    open: Callable
    url: str
    cmd_url: str

    @property
    def hosts(self):
        url_data = self.open(self.url)
        soup = bs(url_data.read(), "html.parser")
        host_links = soup.find_all(lambda tag: tag.name == "a" and "title" in tag.attrs)
        return [h.string for h in host_links]

    async def refresh(self, host):
        reschedule_command = dict(
            cmd_typ=17,
            cmd_mod=2,
            host=host,
            start_time=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            force_check="on",
            btnSubmit="Commit",
        )
        data = urllib.parse.urlencode(reschedule_command).encode()
        self.open(urllib.request.Request(self.cmd_url, data=data))

    async def find_alerts(self, hosts=None, **severities) -> NagiosAlerts:
        classes = {
            "critical": "statusBGCRITICAL",
            "pending": "statusPENDING",
            "ok": "statusOK",
        }
        for host in hosts or []:
            await self.refresh(host)
        url_data = self.open(self.url)
        soup = bs(url_data.read(), "html.parser")
        alerts = {
            severity: soup.find_all("td", class_=classes[severity.lower()])
            for severity in severities
        }
        return NagiosAlerts(alerts, severities)

    async def critical_alerts_by_app(self, *apps: str, hosts=None):
        alerts = await self.find_alerts(hosts=hosts, critical=lambda c: len(c) > 0)
        criticals = alerts["critical"]

        if criticals:
            found = {app: [] for app in apps}
            for c in criticals:
                for link in c.find_all("a", recursive=False):
                    for app in apps:
                        if app in link.string:
                            qs = urllib.parse.parse_qs(link.attrs["href"])
                            data = qs["host"][0], qs["service"][0]
                            found[app].append(data)
            if all(app_crits for app_crits in found.values()):
                log.info(f"Found critical errors in {', '.join(apps)}:")
                for app, app_crits in found.items():
                    for crit_host, crit_service in app_crits:
                        log.info(f"{app} - {crit_service}")
                return found
        return False

    async def wait_for_settle(self, stage, hosts=None, **kwds):
        """Wait for nagios to show no critical and no pending alerts."""
        timeout_msg = (
            "Failed to stabalize nagios after " + stage + "\nalerts: \n{}\n---"
        )
        await retry_async_with_timeout(
            self.find_alerts,
            args=tuple(),
            kwds=dict(hosts=hosts, critical=lambda c: not c, pending=lambda p: not p),
            timeout_msg=timeout_msg,
            **kwds,
        )


@pytest.fixture()
async def nagios(model, tools):
    """Deploys nagios into the model

    1) Deploy nagios and nrpe
    2) login to nagios
    3) verify nagios has no errors and none pending
    ... yield nagios url for tests ...
    4) Remove nagios and nrpe
    """
    series = os.environ["SERIES"]
    if series in ("xenial",):
        pytest.skip(f"skipping unsupported series {series}")

    # 1a) deploy npre and nagios
    log.info("deploying nagios and nrpe")
    nagios, nrpe = map(model.applications.get, ("nagios", "nrpe"))
    deployed = dict(nagios=bool(nagios), nrpe=bool(nrpe))
    if not deployed["nagios"]:
        nagios = await model.deploy("nagios", series="bionic")
        await nagios.expose()
    if not deployed["nrpe"]:
        excludes = [
            "/snap/",
            "/sys/fs/cgroup",
            "/run/containerd",
            "/var/lib/docker",
            "/run/credentials",
            "/run/systemd/incoming",
        ]
        nrpe = await model.deploy(
            "nrpe",
            series=series,
            config=dict(
                ro_filesystem_excludes=",".join(excludes),
                nagios_hostname_type="unit",  # always use unit names for hostnames in nagios
                space_check="check: disabled",  # don't run the space_check
                swap="",
                swap_activity="",
            ),
            num_units=0,
            channel="stable",
        )
    # 1b) relate apps to nrpe (and ignore ceph-mon and ceph-osd)
    unmonitored_apps = ["nrpe", "ceph-mon", "ceph-osd"]
    for each, related in model.applications.items():
        if each not in unmonitored_apps and not any(
            "nrpe:" in str(rel) for rel in related.relations
        ):
            await model.add_relation("nrpe", each)
    log.info("waiting for cluster to settle...")
    await tools.juju_wait()

    # 2) login to nagios
    cmd = "cat /var/lib/juju/nagios.passwd"
    output = await juju_run(nagios.units[0], cmd, timeout=10)
    assert output.status == "completed"
    login_passwd = output.stdout.strip()

    pwd_mgr = urllib.request.HTTPPasswordMgrWithDefaultRealm()
    url_base = "http://{}".format(nagios.units[0].public_address)
    pwd_mgr.add_password(None, url_base, "nagiosadmin", login_passwd)
    handler = urllib.request.HTTPBasicAuthHandler(pwd_mgr)
    opener = urllib.request.build_opener(handler)
    status_url = f"{url_base}/cgi-bin/nagios3/status.cgi?host=all&limit=500"
    cmd_url = f"{url_base}/cgi-bin/nagios3/cmd.cgi"

    # 3) wait for nagios to settle
    log.info("waiting for nagios to settle")
    nagios_api = NagiosApi(opener.open, status_url, cmd_url)
    await nagios_api.wait_for_settle(
        stage="after deployment",
        timeout_insec=60 * 15,
    )

    yield nagios_api

    if not deployed["nagios"]:
        await model.remove_application("nagios")
    if not deployed["nrpe"]:
        await model.remove_application("nrpe")
    await tools.juju_wait()


@pytest.mark.skip_if_version(lambda v: v < (1, 17))
@pytest.mark.clouds(["vsphere"])  # bionic image no longer deployable on ec2 cloud
@pytest.mark.skip("Feature removed in ops rewrite")
async def test_nagios(model, nagios: NagiosApi):
    """This test verifies the nagios relation is working
    properly. This requires:

    1) force api server issues
    2) verify nagios errors show for control-planes and workers
    3) fix api server
    4) break a worker's kubelet
    5) verify nagios errors for worker
    6) fix worker
    """

    log.info("starting nagios test")
    control_plane = model.applications["kubernetes-control-plane"]
    apps_with_alerts = ("kubernetes-control-plane", "kubernetes-worker")
    hosts_from_apps = set(
        h for h in nagios.hosts if any(app in h for app in apps_with_alerts)
    )

    try:
        # 1) break all the things
        log.info("breaking api server")
        await control_plane.set_config({"api-extra-args": "broken=true"})

        # 2) make sure nagios is complaining for kubernetes-control-plane
        #    AND kubernetes-worker
        log.info("Verifying complaints")
        await retry_async_with_timeout(
            nagios.critical_alerts_by_app,
            ("kubernetes-control-plane", "kubernetes-worker"),
            kwds=dict(hosts=hosts_from_apps),
            timeout_insec=10 * 60,
            timeout_msg="Failed to find critical errors in control-plane and worker after 10m.",
            retry_interval_insec=30,
        )
    finally:
        # 3) fix api
        log.info("Fixing API server")
        await control_plane.set_config({"api-extra-args": ""})

    # wait for complaints to go away
    await nagios.wait_for_settle(
        stage="restoring API Server", timeout_insec=10 * 60, hosts=hosts_from_apps
    )

    try:
        # 4) break worker
        log.info("Breaking workers")
        workers = model.applications["kubernetes-worker"]
        await workers.set_config({"kubelet-extra-args": "broken=true"})

        # 5) verify nagios is complaining about worker
        log.info("Verifying complaints")
        await retry_async_with_timeout(
            nagios.critical_alerts_by_app,
            ("kubernetes-worker",),
            kwds=dict(hosts=hosts_from_apps),
            timeout_insec=10 * 60,
            timeout_msg="Failed to find critical errors in worker after 10m.",
            retry_interval_insec=30,
        )
    finally:
        # 9) Fix worker
        await workers.set_config({"kubelet-extra-args": ""})

    # wait for complaints to go away
    await nagios.wait_for_settle(
        stage="restoring worker kubelets", timeout_insec=10 * 60, hosts=hosts_from_apps
    )


@pytest.mark.skip("Failing and being investigated on possible deprecation")
@pytest.mark.skip("Feature removed in ops rewrite")
async def test_nfs(model, tools):
    # setup
    log.info("deploying nfs")
    await model.deploy("nfs")

    log.info("adding relations")
    await model.add_relation("nfs", "kubernetes-worker")
    log.info("waiting...")
    await tools.juju_wait()

    log.info("waiting for nfs pod to settle")
    unit = model.applications["kubernetes-control-plane"].units[0]
    await retry_async_with_timeout(
        verify_ready,
        (unit, "po", ["nfs-client-provisioner"]),
        timeout_msg="NFS pod not ready!",
    )
    # create pod that writes to a pv from nfs
    # yep, I called it default :-/
    await validate_storage_class(model, "default", "NFS")

    # cleanup
    await model.applications["nfs"].destroy()
    await tools.juju_wait()


@pytest.fixture(scope="class")
async def ceph_apps(model, tools):
    # setup
    series = os.environ["SERIES"]
    series_idx = SERIES_ORDER.index(series)
    ceph_config = {}
    ceph_charms_channel = "quincy/stable"
    if series_idx > SERIES_ORDER.index("jammy"):
        pytest.fail("ceph_charm_channel is undefined past jammy")

    all_apps = ["ceph-mon", "ceph-osd", "ceph-fs", "ceph-csi"]
    if all(a in model.applications for a in all_apps):
        if not tools.use_existing_ceph_apps:
            pytest.skip("Skipped since ceph apps are already installed")

        # allow currently deployed ceph apps to run tests
        mon, osd, fs, csi = (model.applications[a] for a in all_apps)
        await model.wait_for_idle(status="active", timeout=20 * 60)
        yield dict(mon=mon, osd=osd, fs=fs, csi=csi)
        return

    log.info("deploying ceph mon")
    ceph_mon = await model.deploy(
        "ceph-mon",
        num_units=3,
        series=series,
        config=ceph_config,
        channel=ceph_charms_channel,
    )
    cs = {
        "osd-devices": {"size": 8 * 1024, "count": 1},
        "osd-journals": {"size": 8 * 1024, "count": 1},
    }
    log.info("deploying ceph osd")
    ceph_osd = await model.deploy(
        "ceph-osd",
        storage=cs,
        num_units=3,
        series=series,
        config=ceph_config,
        constraints="root-disk=32G",
        channel=ceph_charms_channel,
    )

    log.info("deploying ceph fs")
    ceph_fs = await model.deploy(
        "ceph-fs",
        num_units=1,
        series=series,
        config=ceph_config,
        channel=ceph_charms_channel,
    )

    log.info("deploying ceph-csi")
    ceph_csi = await model.deploy(
        "ceph-csi",
        series=series,
        num_units=0,
        config={
            "cephfs-enable": "true",
            "namespace": "kube-system",
        },
        channel=tools.charm_channel,
    )

    log.info("adding relations")
    await model.integrate("ceph-mon", "ceph-osd")
    await model.integrate("ceph-mon", "ceph-fs")
    await model.integrate("ceph-mon:client", "ceph-csi:ceph-client")
    await model.integrate("kubernetes-control-plane", "ceph-csi:kubernetes")
    log.info("waiting for charm deployment...")
    try:
        await model.wait_for_idle(status="active", timeout=40 * 60)
        yield dict(mon=ceph_mon, osd=ceph_osd, fs=ceph_fs, csi=ceph_csi)
    finally:
        # cleanup
        log.info("removing ceph applications")

        # LP:1929537 get ceph-fs outta there with fire.
        juju_apps = {
            "ceph-fs": dict(force=True),
            "ceph-mon": dict(),
            "ceph-osd": dict(destroy_storage=True),
            "ceph-csi": dict(),
        }

        async def burn_units(app, status="error"):
            """Remove any units from the model if they currently match `status`."""
            await asyncio.gather(
                *(
                    model.destroy_unit(unit.name)
                    for unit in model.applications[app].units
                    if unit.agent_status == status
                )
            )

        for app in set(juju_apps) & set(model.applications):
            # remove any applications currently deployed into the model
            await burn_units(app)
            await model.remove_application(app, **juju_apps[app])

        log.info("waiting for charm removal...")
        # block until no juju_apps are in the current model
        await model.block_until(lambda: not (set(juju_apps) & set(model.applications)))


async def test_series_upgrade(model, tools):
    if not tools.is_series_upgrade:
        pytest.skip("No series upgrade argument found")
    skipped = True
    for machine in model.machines.values():
        old_series = machine.series
        try:
            new_series = SERIES_ORDER[SERIES_ORDER.index(old_series) + 1]
            skipped = False
        except IndexError:
            log.info(f"no supported series to upgrade machine {machine.tag} to")
            continue
        except ValueError:
            log.info(
                f"unrecognized series to upgrade machine {machine.tag} from: "
                f"{old_series}"
            )
            continue
        await refresh_openstack_charms(machine, new_series, tools)
        await prep_series_upgrade(machine, new_series, tools)
        await do_series_upgrade(machine)
        await finish_series_upgrade(machine, tools, new_series)
    if skipped:
        pytest.skip("no supported series to upgrade to")
    expected_messages = {
        "kubernetes-control-plane": "Kubernetes control-plane running.",
        "kubernetes-worker": "Kubernetes worker running.",
    }
    for app, message in expected_messages.items():
        for unit in model.applications[app].units:
            assert unit.workload_status_message == message


@pytest.mark.clouds(["openstack"])
async def test_cinder(model, tools):
    assert "openstack-integrator" in model.applications, "Missing integrator"
    # create pod that writes to a pv from cinder
    await validate_storage_class(model, "cdk-cinder", "Cinder")


@pytest.mark.clouds(["openstack"])
@pytest.mark.usefixtures("teardown_microbot")
async def test_octavia(model, tools):
    # TODO: Update the microbot deployment mechanism since the action has been deprecated.
    assert "openstack-integrator" in model.applications, "Missing integrator"
    log.info("Deploying microbot")
    unit = model.applications["kubernetes-worker"].units[0]
    await juju_run_action(unit, "microbot", replicas=3)
    log.info("Replacing microbot service with Octavia LB")
    await kubectl(model, "delete svc microbot")
    await retry_async_with_timeout(
        verify_deleted,
        (unit, "svc", ["microbot"]),
        timeout_msg="Timed out waiting for microbot service removal",
    )
    await kubectl(
        model,
        "expose deployment microbot --type=LoadBalancer --port=80 --target-port=80",
    )
    await retry_async_with_timeout(
        verify_ready,
        (unit, "pod,svc", ["microbot"]),
        timeout_msg="Timed out waiting for new microbot service",
    )
    ingress_address = await get_svc_ingress(model, "microbot", timeout=5 * 60)
    resp = await tools.requests_get(
        f"http://{ingress_address}",
        proxies={"http": None, "https": None},
    )
    assert resp.status_code == 200


@pytest.mark.skip("Getting further")
async def test_containerd_to_docker(model, tools):
    """
    Assume we're starting with containerd, replace
    with Docker and then revert to containerd.

    :param model: Object
    :return: None
    """
    containerd_app = model.applications["containerd"]

    await containerd_app.remove()
    await tools.juju_wait(x="kubernetes-worker")
    # Block until containerd's removed, ignore `blocked` worker.

    docker_app = await model.deploy(
        "docker", num_units=0, channel=tools.charm_channel  # Subordinate.
    )

    await docker_app.add_relation("docker", "kubernetes-control-plane")

    await docker_app.add_relation("docker", "kubernetes-worker")

    await tools.juju_wait()
    # If we settle, it's safe to
    # assume Docker is now running
    # workloads.

    await docker_app.remove()
    await tools.juju_wait(x="kubernetes-worker")
    # Block until docker's removed, ignore `blocked` worker.

    containerd_app = await model.deploy(
        "containerd", num_units=0, channel=tools.charm_channel  # Subordinate.
    )

    await containerd_app.add_relation("containerd", "kubernetes-control-plane")

    await containerd_app.add_relation("containerd", "kubernetes-worker")

    await tools.juju_wait()


async def test_sriov_cni(model, tools, addons_model):
    if "sriov-cni" not in addons_model.applications:
        pytest.skip("sriov-cni is not deployed")

    apps = ["kubernetes-worker", "kubernetes-control-plane"]
    units = (u for app in apps for u in model.applications[app].units)
    failures = []
    for unit in units:
        run = await juju_run(unit, "[ -x /opt/cni/bin/sriov ]", check=False)
        if not run.success:
            failures.append(f"sriov binary was missing on {unit.name}")
    assert not failures, "\n".join(failures)


async def test_sriov_network_device_plugin(model, tools, addons_model):
    if "sriov-network-device-plugin" not in addons_model.applications:
        pytest.skip("sriov-network-device-plugin is not deployed")

    app = addons_model.applications["sriov-network-device-plugin"]
    config = await app.get_config()
    resource_list = yaml.safe_load(config["resource-list"]["value"])
    resource_prefix = config["resource-prefix"]["value"]
    resource_names = [
        resource_prefix + "/" + resource["resourceName"] for resource in resource_list
    ]

    control_plane_unit = model.applications["kubernetes-control-plane"].units[0]
    cmd = "/snap/bin/kubectl --kubeconfig /root/.kube/config get node -o json"
    raw_output = await run_until_success(control_plane_unit, cmd)
    data = json.loads(raw_output)
    failures = []
    for node in data["items"]:
        node_name = node["metadata"]["name"]
        capacity = node["status"]["capacity"]
        for resource_name in resource_names:
            if resource_name not in capacity:
                failures.append(
                    f"'{resource_name}' isn't in node's capacity ({node_name})\n{json.dumps(capacity, indent=2)}"
                )
    assert not failures, "\n".join(failures)
