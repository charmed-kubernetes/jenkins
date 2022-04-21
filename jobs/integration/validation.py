import asyncio
import base64

import backoff
import ipaddress
import json
import os
import requests
import traceback
import yaml
import re
import random
import pytest
import logging
import click
from asyncio_extras import async_contextmanager
from async_generator import yield_
from base64 import b64encode

# from cilib import log
from datetime import datetime
from pprint import pformat
from tempfile import NamedTemporaryFile
from types import SimpleNamespace
from .utils import (
    timeout_for_current_task,
    retry_async_with_timeout,
    scp_to,
    scp_from,
    disable_source_dest_check,
    find_entities,
    verify_deleted,
    verify_ready,
    is_localhost,
    validate_storage_class,
    SERIES_ORDER,
    prep_series_upgrade,
    do_series_upgrade,
    finish_series_upgrade,
    kubectl,
    juju_run,
    get_ipv6_addr,
    vault,
    vault_status,
    get_svc_ingress,
)
import urllib.request
from .logger import log
from bs4 import BeautifulSoup as bs

# Quiet the noise
logging.getLogger("websockets.protocol").setLevel(logging.INFO)
# bump up juju debug
logging.getLogger("juju").setLevel(logging.INFO)


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
    master = model.applications["kubernetes-control-plane"]
    for unit in master.units:
        search = "ps -ef | grep {} | grep apiserver".format(argument)
        action = await unit.run(search)
        assert action.status == "completed"
        raw_output = action.data["results"].get("Stdout", "")
        if len(raw_output.splitlines()) != 1:
            return False
    return True


async def run_until_success(unit, cmd, timeout_insec=None):
    while True:
        action = await unit.run(cmd, timeout=timeout_insec)
        if (
            action.status == "completed"
            and "results" in action.data
            and action.data["results"]["Code"] == "0"
        ):
            return action.data["results"].get("Stdout", "")
        else:
            click.echo(
                "Action " + action.status + ". Command failed on unit " + unit.entity_id
            )
            click.echo("cmd: " + cmd)
            if "results" in action.data:
                click.echo("code: " + action.data["results"]["Code"])
                click.echo(
                    "stdout:\n" + action.data["results"].get("Stdout", "").strip()
                )
                click.echo(
                    "stderr:\n" + action.data["results"].get("Stderr", "").strip()
                )
                click.echo("Will retry...")
            await asyncio.sleep(5)


async def run_and_check(desc, unit, cmd, timeout=None):
    result = await unit.run(cmd, timeout=timeout)
    status = result.status
    code = result.data.get("results", {}).get("Code")
    stdout = result.data.get("results", {}).get("Stdout").strip()
    stderr = result.data.get("results", {}).get("Stderr").strip()
    assert (status, code) == ("completed", "0"), (
        f"Failed to {desc}:\n"
        f"  status={status}\n"
        f"  code={code}\n"
        f"  stdout={stdout}\n"
        f"  stderr={stderr}"
    )
    return stdout


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


@async_contextmanager
async def assert_hook_occurs_on_all_units(app, hook):
    started_units = set()
    finished_units = set()

    for unit in app.units:

        @unit.on_change
        async def on_change(delta, old, new, model):
            unit_id = new.entity_id
            if new.agent_status_message == "running " + hook + " hook":
                started_units.add(unit_id)
            if new.agent_status == "idle" and unit_id in started_units:
                finished_units.add(unit_id)

    await yield_()

    click.echo("assert_hook_occurs_on_all_units: waiting for " + hook + " hook")
    while len(finished_units) < len(app.units):
        await asyncio.sleep(5)


async def set_config_and_wait(app, config, tools, timeout_secs=None):
    current_config = await app.get_config()

    if all(config[key] == current_config[key]["value"] for key in config):
        click.echo("set_config_and_wait: new config identical to current, skipping")
        return

    async with assert_hook_occurs_on_all_units(app, "config-changed"):
        await app.set_config(config)
        await tools.juju_wait(timeout_secs=timeout_secs)


async def reset_audit_config(master_app, tools):
    config = await master_app.get_config()
    await set_config_and_wait(
        master_app,
        {
            "audit-policy": config["audit-policy"]["default"],
            "audit-webhook-config": config["audit-webhook-config"]["default"],
            "api-extra-args": config["api-extra-args"]["default"],
        },
        tools,
    )


# START TESTS
async def test_auth_file_propagation(model, tools):
    """Validate that changes to /root/cdk/basic_auth.csv on the leader master
    unit are propagated to the other master units.

    """
    # Get a leader and non-leader unit to test with
    masters = model.applications["kubernetes-control-plane"]
    if len(masters.units) < 2:
        pytest.skip("Auth file propagation test requires multiple masters")

    for master in masters.units:
        if await master.is_leader_from_status():
            leader = master
        else:
            follower = master

    # Change basic_auth.csv on the leader, and get its md5sum
    leader_md5 = await run_until_success(
        leader,
        "echo test,test,test >> /root/cdk/basic_auth.csv && "
        "md5sum /root/cdk/basic_auth.csv",
    )

    # Check that md5sum on non-leader matches
    await run_until_success(
        follower, 'md5sum /root/cdk/basic_auth.csv | grep "{}"'.format(leader_md5)
    )

    # Cleanup (remove the line we added)
    await run_until_success(leader, "sed -i '$d' /root/cdk/basic_auth.csv")
    await tools.juju_wait()


@pytest.mark.flaky(max_runs=5, min_passes=1)
async def test_status_messages(model):
    """Validate that the status messages are correct."""
    expected_messages = {
        "kubernetes-control-plane": "Kubernetes control-plane running.",
        "kubernetes-worker": "Kubernetes worker running.",
    }
    for app, message in expected_messages.items():
        for unit in model.applications[app].units:
            assert unit.workload_status_message == message


async def test_snap_versions(model):
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
        track = channel.split("/")[0]
        for unit in app.units:
            action = await unit.run("snap list")
            assert action.status == "completed"
            raw_output = action.data["results"].get("Stdout", "")
            # Example of the `snap list` output format we're expecting:
            # Name        Version  Rev   Developer  Notes
            # conjure-up  2.1.5    352   canonical  classic
            # core        16-2     1689  canonical  -
            # kubectl     1.6.2    27    canonical  classic
            lines = raw_output.splitlines()[1:]
            snap_versions = dict(line.split()[:2] for line in lines)
            for snap in snaps:
                snap_version = snap_versions[snap]
                if not snap_version.startswith(track + "."):
                    click.echo(
                        "Snap {} is version {} and not {}".format(
                            snap, snap_version, track + "."
                        )
                    )
                assert snap_version.startswith(track + ".")


async def test_rbac(model):
    """When RBAC is enabled, validate kubelet creds cannot get ClusterRoles"""
    app = model.applications["kubernetes-control-plane"]
    config = await app.get_config()
    if "RBAC" not in config["authorization-mode"]["value"]:
        pytest.skip("Cluster does not have RBAC enabled")

    cmd = "/snap/bin/kubectl --kubeconfig /root/cdk/kubeconfig get clusterroles"
    worker = model.applications["kubernetes-worker"].units[0]
    await run_until_success(worker, cmd + " 2>&1 | grep Forbidden")


@pytest.mark.clouds(["ec2"])
async def test_microbot(model, tools):
    """Validate the microbot action"""
    unit = model.applications["kubernetes-worker"].units[0]
    action = await unit.run_action("microbot", delete=True)
    await action.wait()
    action = await unit.run_action("microbot", replicas=3)
    await action.wait()
    assert action.status == "completed"
    while True:
        try:
            resp = await tools.requests.get(
                "http://" + action.data["results"]["address"],
                proxies={"http": None, "https": None},
            )
            if resp.status_code == 200:
                return
        except requests.exceptions.ConnectionError:
            click.echo(
                "Caught connection error attempting to hit xip.io, "
                "retrying. Error follows:"
            )
            click.echo(traceback.print_exc())
        await asyncio.sleep(60)


@pytest.mark.clouds(["ec2", "vsphere"])
@backoff.on_exception(backoff.expo, TypeError, max_tries=5)
async def test_dashboard(model, log_dir, tools):
    """Validate that the dashboard is operational"""
    unit = model.applications["kubernetes-control-plane"].units[0]
    with NamedTemporaryFile() as f:
        await scp_from(unit, "config", f.name, tools.controller_name, tools.connection)
        with open(f.name, "r") as stream:
            config = yaml.safe_load(stream)

    async def query_dashboard(url, config):
        # handle pre 1.19 authentication
        try:
            user = config["users"][0]["user"]["username"]
            password = config["users"][0]["user"]["password"]
            auth = tools.requests.auth.HTTPBasicAuth(user, password)
            resp = await tools.requests.get(url, auth=auth, verify=False)
        except KeyError:
            token = config["users"][0]["user"]["token"]
            headers = {"Authorization": f"Bearer {token}"}
            resp = await tools.requests.get(url, headers=headers, verify=False)
        return resp

    # make sure we can hit the api-server
    url = config["clusters"][0]["cluster"]["server"]

    can_access_dashboard = await query_dashboard(url, config)
    assert can_access_dashboard.status_code == 200

    # get k8s version
    app_config = await model.applications["kubernetes-control-plane"].get_config()
    channel = app_config["channel"]["value"]
    # if we do not detect the version from the channel eg edge, stable etc
    # we should default to the latest dashboard url format
    k8s_version = (2, 0)
    if "/" in channel:
        version_string = channel.split("/")[0]
        k8s_version = tuple(int(q) for q in re.findall("[0-9]+", version_string)[:2])

    # construct the url to the dashboard login form
    if k8s_version < (1, 16):
        dash_ns = "kube-system"
    else:
        dash_ns = "kubernetes-dashboard"
    url = (
        "{server}/api/v1/namespaces/{ns}/services/https:kubernetes-dashboard:"
        "/proxy/#!/login"
    ).format(server=config["clusters"][0]["cluster"]["server"], ns=dash_ns)

    click.echo("Waiting for dashboard to stabilize...")

    async def dashboard_present(url, config):
        resp = await query_dashboard(url, config)
        if resp.status_code == 200 and "Dashboard" in resp.text:
            return True
        return False

    await retry_async_with_timeout(
        verify_ready,
        (unit, "po", ["kubernetes-dashboard"], "-n {ns}".format(ns=dash_ns)),
        timeout_msg="Unable to find kubernetes dashboard before timeout",
    )

    await retry_async_with_timeout(
        dashboard_present, (url, config), timeout_msg="Unable to reach dashboard"
    )


async def test_kubelet_anonymous_auth_disabled(model, tools):
    """Validate that kubelet has anonymous auth disabled"""

    async def validate_unit(unit):
        await unit.run("open-port 10250")
        address = unit.public_address
        url = "https://%s:10250/pods/" % address
        for attempt in range(0, 120):  # 2 minutes
            try:
                response = await tools.requests.get(
                    url, verify=False, proxies={"http": None, "https": None}
                )
                assert response.status_code == 401  # Unauthorized
                break
            except requests.exceptions.ConnectionError:
                log(
                    "Failed to connect to kubelet on {}; retrying in 10s".format(
                        unit.name
                    )
                )
                await asyncio.sleep(10)
        else:
            output = await unit.run("systemctl status --no-pager snap.kubelet.daemon")
            stdout = output.results.get("Stdout", "")
            stderr = output.results.get("Stderr", "")
            if "active (running)" not in stdout:
                raise AssertionError(
                    "kubelet not running on {}: {}".format(unit.name, stdout or stderr)
                )
            else:
                await unit.run("which netstat || apt install net-tools")
                output = await unit.run("netstat -tnlp")
                stdout = output.results.get("Stdout", "")
                stderr = output.results.get("Stderr", "")
                raise AssertionError(
                    "Unable to connect to kubelet on {}: {}".format(
                        unit.name,
                        stdout or stderr,
                    )
                )

    units = model.applications["kubernetes-worker"].units
    await asyncio.gather(*(validate_unit(unit) for unit in units))


@pytest.mark.skip_apps(["canal", "calico", "tigera-secure-ee"])
async def test_network_policies(model, tools):
    """Apply network policy and use two busyboxes to validate it."""
    here = os.path.dirname(os.path.abspath(__file__))
    unit = model.applications["kubernetes-control-plane"].units[0]

    # Clean-up namespace from any previous runs.
    cmd = await unit.run(
        "/snap/bin/kubectl --kubeconfig /root/.kube/config delete ns netpolicy"
    )
    assert cmd.status == "completed"
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
    )
    await scp_to(
        os.path.join(here, "templates", "restrict.yaml"),
        unit,
        "restrict.yaml",
        tools.controller_name,
        tools.connection,
    )
    cmd = await unit.run(
        "/snap/bin/kubectl --kubeconfig /root/.kube/config create -f /home/ubuntu/netpolicy-test.yaml"
    )
    if not cmd.results["Code"] == "0":
        click.echo("Failed to create netpolicy test!")
        click.echo(cmd.results)
    assert cmd.status == "completed" and cmd.results["Code"] == "0"
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
        cmd_good = await unit.run(query_from_good)
        cmd_bad = await unit.run(query_from_bad)
        if (
            cmd_good.status == "completed"
            and cmd_bad.status == "completed"
            and "index.html" in cmd_good.data["results"].get("Stderr", "")
            and "index.html" in cmd_bad.data["results"].get("Stderr", "")
        ):
            return True
        return False

    await retry_async_with_timeout(
        get_to_networkpolicy_service,
        (),
        timeout_msg="Failed to query nginx.netpolicy even before applying restrictions",
    )

    # Apply network policy and retry getting to nginx.
    # This time the policy should block us.
    cmd = await unit.run(
        "/snap/bin/kubectl --kubeconfig /root/.kube/config create -f /home/ubuntu/restrict.yaml"
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
        cmd_good = await unit.run(query_from_good)
        cmd_bad = await unit.run(query_from_bad)
        if (
            cmd_good.status == "completed"
            and cmd_bad.status == "completed"
            and "foo.html" in cmd_good.data["results"].get("Stderr", "")
            and "timed out" in cmd_bad.data["results"].get("Stderr", "")
        ):
            return True
        return False

    await retry_async_with_timeout(
        get_to_restricted_networkpolicy_service,
        (),
        timeout_msg="Failed query restricted nginx.netpolicy",
    )

    # Clean-up namespace from next runs.
    cmd = await unit.run(
        "/snap/bin/kubectl --kubeconfig /root/.kube/config delete ns netpolicy"
    )
    assert cmd.status == "completed"


async def test_ipv6(model, tools):
    master_app = model.applications["kubernetes-control-plane"]
    master_config = await master_app.get_config()
    service_cidr = master_config["service-cidr"]["value"]
    if all(ipaddress.ip_network(cidr).version != 6 for cidr in service_cidr.split(",")):
        pytest.skip("kubernetes-control-plane not configured for IPv6")

    k8s_version_str = master_app.data["workload-version"]
    k8s_minor_version = tuple(int(i) for i in k8s_version_str.split(".")[:2])

    master = master_app.units[0]
    await kubectl(
        model,
        "create -f - << EOF{}EOF".format(
            f"""
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
  {"ipFamily: IPv6" if k8s_minor_version < (1, 20) else "ipFamilies: [IPv6]"}
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
  {"ipFamily: IPv4" if k8s_minor_version < (1, 20) else "ipFamilies: [IPv4]"}
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
        (master, "svc", ["nginx4", "nginx6"]),
        timeout_msg="Timeout waiting for nginxdualstack services",
    )
    nginx4, nginx6 = await find_entities(master, "svc", ["nginx4", "nginx6"])
    ipv4_port = nginx4["spec"]["ports"][0]["nodePort"]
    ipv6_port = nginx6["spec"]["ports"][0]["nodePort"]
    urls = []
    for worker in model.applications["kubernetes-worker"].units:
        for port in (ipv4_port, ipv6_port):
            action = await worker.run("open-port {}".format(port))
            assert action.status == "completed"
            assert action.results["Code"] == "0"
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
                output = await master.run("curl '{}'".format(url))
                if (
                    output.status == "completed"
                    and output.results["Code"] == "0"
                    and "Kubernetes IPv6 nginx" in output.results["Stdout"]
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
async def test_gpu_support(model, tools):
    """Test gpu support. Should be disabled if hardware
    is not detected and functional if hardware is fine"""

    # See if the workers have nvidia
    workers = model.applications["kubernetes-worker"]
    action = await workers.units[0].run("lspci -nnk")
    nvidia = (
        True if action.results.get("Stdout", "").lower().count("nvidia") > 0 else False
    )

    master_unit = model.applications["kubernetes-control-plane"].units[0]
    if not nvidia:
        # nvidia should not be running
        await retry_async_with_timeout(
            verify_deleted,
            (master_unit, "ds", ["nvidia-device-plugin-daemonset"], "-n kube-system"),
            timeout_msg="nvidia-device-plugin-daemonset is setup without nvidia hardware",
        )
    else:
        # nvidia should be running
        await retry_async_with_timeout(
            verify_ready,
            (master_unit, "ds", ["nvidia-device-plugin-daemonset"], "-n kube-system"),
            timeout_msg="nvidia-device-plugin-daemonset not running",
        )

        # Do an addition on the GPU just be sure.
        # First clean any previous runs
        here = os.path.dirname(os.path.abspath(__file__))
        await scp_to(
            os.path.join(here, "templates", "nvidia-smi.yaml"),
            master_unit,
            "nvidia-smi.yaml",
            tools.controller_name,
            tools.connection,
        )
        await master_unit.run(
            "/snap/bin/kubectl --kubeconfig /root/.kube/config delete -f /home/ubuntu/nvidia-smi.yaml"
        )
        await retry_async_with_timeout(
            verify_deleted,
            (master_unit, "po", ["nvidia-smi"], "-n default"),
            timeout_msg="Cleaning of nvidia-smi pod failed",
        )
        # Run the cuda addition
        cmd = await master_unit.run(
            "/snap/bin/kubectl --kubeconfig /root/.kube/config create -f /home/ubuntu/nvidia-smi.yaml"
        )
        if not cmd.results["Code"] == "0":
            click.echo("Failed to create nvidia-smi pod test!")
            click.echo(cmd.results)
            assert False

        async def cuda_test(master):
            action = await master.run(
                "/snap/bin/kubectl --kubeconfig /root/.kube/config logs nvidia-smi"
            )
            click.echo(action.results.get("Stdout", ""))
            return action.results.get("Stdout", "").count("NVIDIA-SMI") > 0

        await retry_async_with_timeout(
            cuda_test,
            (master_unit,),
            timeout_msg="Cuda test did not pass",
            timeout_insec=1200,
        )


async def test_extra_args(model, tools):
    async def get_filtered_service_args(app, service):
        results = []

        for unit in app.units:
            while True:
                action = await unit.run("pgrep -a " + service)
                assert action.status == "completed"

                if action.data["results"]["Code"] == "0":
                    raw_output = action.data["results"].get("Stdout", "")
                    arg_string = raw_output.partition(" ")[2].partition(" ")[2]
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
            except asyncio.CancelledError:
                click.echo("Dumping locals:\n" + pformat(locals()))
                raise

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
            except asyncio.CancelledError:
                click.echo("Dumping locals:\n" + pformat(locals()))
                raise

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
    k8s_version_str = worker_app.data["workload-version"]
    k8s_minor_version = tuple(int(i) for i in k8s_version_str.split(".")[:2])
    if k8s_minor_version < (1, 10):
        click.echo("skipping, k8s version v" + k8s_version_str)
        return

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
    await set_config_and_wait(
        worker_app, {"kubelet-extra-config": new_extra_config}, tools
    )

    # wait for and validate new maxPods value
    click.echo("waiting for nodes to show new pod capacity")
    master_unit = model.applications["kubernetes-control-plane"].units[0]
    while True:
        cmd = "/snap/bin/kubectl --kubeconfig /root/.kube/config -o yaml get node -l 'juju-application=kubernetes-worker'"
        action = await master_unit.run(str(cmd))
        if action.status == "completed" and action.results["Code"] == "0":
            nodes = yaml.safe_load(action.results.get("Stdout", ""))

            all_nodes_updated = all(
                [node["status"]["capacity"]["pods"] == "111" for node in nodes["items"]]
            )
            if all_nodes_updated:
                break

        await asyncio.sleep(5)

    # validate config.yaml on each worker
    click.echo("validating generated config.yaml files")
    for worker_unit in worker_app.units:
        cmd = "cat /root/cdk/kubelet/config.yaml"
        action = await worker_unit.run(cmd)
        if action.status == "completed" and action.results["Code"] == "0":
            config = yaml.safe_load(action.results.get("Stdout", ""))
            assert config["evictionHard"]["memory.available"] == "200Mi"
            assert config["authentication"]["webhook"]["enabled"] is False
            assert "anonymous" in config["authentication"]
            assert "x509" in config["authentication"]

    # clean up
    await set_config_and_wait(
        worker_app, {"kubelet-extra-config": old_extra_config}, tools
    )


async def test_service_cidr_expansion(model):
    """Expand the service cidr by 1 and verify if kubernetes service is
    updated with the new cluster IP.

    Note the cluster cannot be revert back to the oiriginal service cidr.
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

    cmd = "/snap/bin/kubectl --kubeconfig /root/.kube/config get service kubernetes"
    master = model.applications["kubernetes-control-plane"].units[0]
    output = await master.run(cmd)
    assert output.status == "completed"

    # Check if k8s service ip is changed as per new service cidr
    raw_output = output.data["results"].get("Stdout", "")
    assert new_service_ip_str in raw_output


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
            action = await unit.run(
                "openssl s_client -connect 127.0.0.1:6443 </dev/null 2>/dev/null | openssl x509 -text"
            )
            assert action.status == "completed"
            raw_output = action.data["results"].get("Stdout", "")
            results[unit.name] = raw_output

        # if there is a load balancer, ask it as well
        if lb is not None:
            for unit in lb.units:
                action = await unit.run(
                    "openssl s_client -connect 127.0.0.1:443 </dev/null 2>/dev/null | openssl x509 -text"
                )
                assert action.status == "completed"
                raw_output = action.data["results"].get("Stdout", "")
                results[unit.name] = raw_output

        return results

    async def all_certs_removed():
        certs = await get_server_certs()
        passing = True
        log("Checking for example domain removed from certs...")
        for unit_name, cert in certs.items():
            if example_domain in cert:
                passing = False
                log(f"Example domain still in cert for {unit_name}")
        return passing

    async def all_certs_in_place():
        certs = await get_server_certs()
        passing = True
        log("Checking for example domain added to certs...")
        for unit_name, cert in certs.items():
            if example_domain not in cert:
                passing = False
                if not cert:
                    log(f"Cert empty for {unit_name}")
                else:
                    log(f"Example domain not in cert for {unit_name}")
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


async def test_audit_default_config(model, tools):
    app = model.applications["kubernetes-control-plane"]

    # Ensure we're using default configuration
    await reset_audit_config(app, tools)

    # Verify new entries are being logged
    unit = app.units[0]
    before_date = await get_last_audit_entry_date(app)
    await asyncio.sleep(5)
    await run_until_success(
        unit, "/snap/bin/kubectl --kubeconfig /root/.kube/config get po"
    )
    after_date = await get_last_audit_entry_date(app)
    assert after_date > before_date

    # Verify total log size is less than 1 GB
    raw = await run_until_success(unit, "du -bs /root/cdk/audit")
    size_in_bytes = int(raw.split()[0])
    click.echo("Audit log size in bytes: %d" % size_in_bytes)
    max_size_in_bytes = 1000 * 1000 * 1000 * 1.01  # 1 GB, plus some tolerance
    assert size_in_bytes <= max_size_in_bytes

    # Clean up
    await reset_audit_config(app, tools)


@pytest.mark.flaky(max_runs=5, min_passes=1)
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

    k8s_version_str = app.data["workload-version"]
    k8s_minor_version = tuple(int(i) for i in k8s_version_str.split(".")[:2])
    if k8s_minor_version < (1, 16):
        click.echo("skipping, k8s version v" + k8s_version_str)
        return

    config = await app.get_config()
    old_value = config["enable-metrics"]["value"]
    new_value = not old_value

    await set_config_and_wait(
        app, {"enable-metrics": str(new_value)}, tools, timeout_secs=240
    )
    await check_svc(app, new_value)

    await set_config_and_wait(
        app, {"enable-metrics": str(old_value)}, tools, timeout_secs=240
    )
    await check_svc(app, old_value)


async def test_audit_empty_policy(model, tools):
    app = model.applications["kubernetes-control-plane"]

    # Set audit-policy to blank
    await reset_audit_config(app, tools)
    await set_config_and_wait(app, {"audit-policy": ""}, tools)

    # Verify no entries are being logged
    unit = app.units[0]
    before_date = await get_last_audit_entry_date(app)
    await asyncio.sleep(5)
    await run_until_success(
        unit, "/snap/bin/kubectl --kubeconfig /root/.kube/config get po"
    )
    after_date = await get_last_audit_entry_date(app)
    assert after_date == before_date

    # Clean up
    await reset_audit_config(app, tools)


async def test_audit_custom_policy(model, tools):
    app = model.applications["kubernetes-control-plane"]

    # Set a custom policy that only logs requests to a special namespace
    namespace = "validate-audit-custom-policy"
    policy = {
        "apiVersion": "audit.k8s.io/v1beta1",
        "kind": "Policy",
        "rules": [{"level": "Metadata", "namespaces": [namespace]}, {"level": "None"}],
    }
    await reset_audit_config(app, tools)
    await set_config_and_wait(app, {"audit-policy": yaml.dump(policy)}, tools)

    # Verify no entries are being logged
    unit = app.units[0]
    before_date = await get_last_audit_entry_date(app)
    await asyncio.sleep(5)
    await run_until_success(
        unit, "/snap/bin/kubectl --kubeconfig /root/.kube/config get po"
    )
    after_date = await get_last_audit_entry_date(app)
    assert after_date == before_date

    # Create our special namespace
    namespace_definition = {
        "apiVersion": "v1",
        "kind": "Namespace",
        "metadata": {"name": namespace},
    }
    path = "/tmp/validate_audit_custom_policy-namespace.yaml"
    with NamedTemporaryFile("w") as f:
        json.dump(namespace_definition, f)
        f.flush()
        await scp_to(f.name, unit, path, tools.controller_name, tools.connection)
    await run_until_success(
        unit, "/snap/bin/kubectl --kubeconfig /root/.kube/config create -f " + path
    )

    # Verify our very special request gets logged
    before_date = await get_last_audit_entry_date(app)
    await asyncio.sleep(5)
    await run_until_success(
        unit, "/snap/bin/kubectl --kubeconfig /root/.kube/config get po -n " + namespace
    )
    after_date = await get_last_audit_entry_date(app)
    assert after_date > before_date

    # Clean up
    await run_until_success(
        unit, "/snap/bin/kubectl --kubeconfig /root/.kube/config delete ns " + namespace
    )
    await reset_audit_config(app, tools)


async def test_audit_webhook(model, tools):
    app = model.applications["kubernetes-control-plane"]
    unit = app.units[0]

    async def get_webhook_server_entry_count():
        cmd = (
            "/snap/bin/kubectl --kubeconfig /root/.kube/config logs test-audit-webhook"
        )
        raw = await run_until_success(unit, cmd)
        lines = raw.splitlines()
        count = len(lines)
        return count

    # Deploy an nginx target for webhook
    local_path = os.path.dirname(__file__) + "/templates/test-audit-webhook.yaml"
    remote_path = "/tmp/test-audit-webhook.yaml"
    await scp_to(local_path, unit, remote_path, tools.controller_name, tools.connection)
    cmd = "/snap/bin/kubectl --kubeconfig /root/.kube/config apply -f " + remote_path
    await run_until_success(unit, cmd)

    # Get nginx IP
    nginx_ip = None
    while nginx_ip is None:
        cmd = "/snap/bin/kubectl --kubeconfig /root/.kube/config get po -o json test-audit-webhook"
        raw = await run_until_success(unit, cmd)
        pod = json.loads(raw)
        nginx_ip = pod["status"].get("podIP", None)

    # Set audit config with webhook enabled
    audit_webhook_config = {
        "apiVersion": "v1",
        "kind": "Config",
        "clusters": [
            {"name": "test-audit-webhook", "cluster": {"server": "http://" + nginx_ip}}
        ],
        "contexts": [
            {"name": "test-audit-webhook", "context": {"cluster": "test-audit-webhook"}}
        ],
        "current-context": "test-audit-webhook",
    }
    await reset_audit_config(app, tools)
    await set_config_and_wait(
        app,
        {
            "audit-webhook-config": yaml.dump(audit_webhook_config),
            "api-extra-args": "audit-webhook-mode=blocking",
        },
        tools,
    )

    # Ensure webhook log is growing
    before_count = await get_webhook_server_entry_count()
    await run_until_success(
        unit, "/snap/bin/kubectl --kubeconfig /root/.kube/config get po"
    )
    after_count = await get_webhook_server_entry_count()
    assert after_count > before_count

    # Clean up
    await reset_audit_config(app, tools)
    cmd = (
        "/snap/bin/kubectl --kubeconfig /root/.kube/config delete --ignore-not-found -f "
        + remote_path
    )
    await run_until_success(unit, cmd)


@pytest.fixture()
async def any_keystone(model, apps_by_charm, tools):
    def _find_relation(*specs):
        for rel in model.relations:
            if rel.matches(*specs):
                yield rel

    keystone_apps = apps_by_charm("keystone")
    masters = model.applications["kubernetes-control-plane"]
    k8s_version_str = masters.data["workload-version"]
    k8s_minor_version = tuple(int(i) for i in k8s_version_str.split(".")[:2])
    if k8s_minor_version < (1, 12):
        pytest.skip(f"skipping, k8s version v{k8s_version_str} isn't supported")
        return

    keystone_creds = "kubernetes-control-plane:keystone-credentials"
    if len(keystone_apps) > 1:
        pytest.fail(f"More than one keystone app available {','.join(keystone_apps)}")
    elif len(keystone_apps) == 1:
        # One keystone found, ensure related to kubernetes-control-plane
        keystone, *_ = keystone_apps.values()
        credentials_rel = list(_find_relation(keystone_creds))
        if not credentials_rel:
            await keystone.add_relation("identity-credentials", keystone_creds)
            await tools.juju_wait()

        keystone_master = random.choice(keystone.units)
        action = await keystone_master.run("leader-get admin_passwd")
        admin_password = action.results.get("Stdout", "").strip()

        # Work around the following bugs which lead to the CA used by Keystone not being passed along
        # and honored from the keystone-credentials relation itself by getting the CA directly from Vault and
        # passing it in via explicit config.
        #   * https://bugs.launchpad.net/charm-keystone/+bug/1954835
        #   * https://bugs.launchpad.net/charm-kubernetes-control-plane/+bug/1954838
        keystone_ssl_ca = (await masters.get_config())["keystone-ssl-ca"]["value"]
        if not keystone_ssl_ca:
            vault_root_ca = None
            vault_apps = apps_by_charm("vault")
            for name, vault_app in vault_apps.items():
                vault_tls = f"{name}:certificates"
                rels = set(
                    app.name
                    for rel in _find_relation(vault_tls)
                    for app in rel.applications
                )
                if all(
                    name in rels
                    for name in [
                        "kubernetes-control-plane",
                        "kubernetes-worker",
                        keystone.name,
                    ]
                ):
                    vault_unit = random.choice(vault_app.units)
                    action = await vault_unit.run_action("get-root-ca")
                    await action.wait()
                    assert action.status not in ("pending", "running", "failed")
                    vault_root_ca = action.results.get("output")
                    if vault_root_ca:
                        vault_root_ca = base64.b64encode(
                            vault_root_ca.encode("ascii")
                        ).decode("ascii")
                        break

            if vault_root_ca:
                await masters.set_config({"keystone-ssl-ca": vault_root_ca})

        yield SimpleNamespace(app=keystone, admin_password=admin_password)

        if not credentials_rel:
            await keystone.destroy_relation("identity-credentials", keystone_creds)
            await tools.juju_wait()

        await masters.set_config({"keystone-ssl-ca": keystone_ssl_ca})
    else:
        # No keystone available, add/setup one
        admin_password = "testpw"
        keystone = await model.deploy(
            "keystone",
            series="bionic",
            config={
                "admin-password": admin_password,
                "preferred-api-version": "3",
                "openstack-origin": "cloud:bionic-rocky",
            },
        )
        await model.deploy(
            "percona-cluster",
            config={"innodb-buffer-pool-size": "256M", "max-connections": "1000"},
        )

        await model.add_relation(keystone_creds, "keystone:identity-credentials")
        await model.add_relation("keystone:shared-db", "percona-cluster:shared-db")
        await tools.juju_wait()

        yield SimpleNamespace(app=keystone, admin_password=admin_password)

        # cleanup
        await model.applications["keystone"].destroy()
        await tools.juju_wait()
        await model.applications["percona-cluster"].destroy()
        await tools.juju_wait()

        # apparently, juju-wait will consider the model settled before an
        # application has fully gone away (presumably, when all units are gone) but
        # but having a dying percona-cluster in the model can break the vault test
        try:
            await model.block_until(
                lambda: "percona-cluster" not in model.applications, timeout=120
            )
        except asyncio.TimeoutError:
            pytest.fail("Timed out waiting for percona-cluster to go away")


@pytest.mark.skip_arch(["aarch64"])
@pytest.mark.clouds(["ec2", "vsphere"])
async def test_keystone(model, tools, any_keystone):
    masters = model.applications["kubernetes-control-plane"]

    # save off config
    config = await model.applications["kubernetes-control-plane"].get_config()

    # verify kubectl config file has keystone in it
    one_master = random.choice(masters.units)
    for i in range(60):
        action = await one_master.run("cat /home/ubuntu/config")
        if "client-keystone-auth" in action.results.get("Stdout", ""):
            break
        click.echo("Unable to find keystone information in kubeconfig, retrying...")
        await asyncio.sleep(10)

    assert "client-keystone-auth" in action.results.get("Stdout", "")

    # verify kube-keystone.sh exists
    one_master = random.choice(masters.units)
    action = await one_master.run("cat /home/ubuntu/kube-keystone.sh")
    assert "OS_AUTH_URL" in action.results.get("Stdout", "")

    # verify webhook enabled on apiserver
    await wait_for_process(model, "authentication-token-webhook-config-file")
    one_master = random.choice(masters.units)
    action = await one_master.run("sudo cat /root/cdk/keystone/webhook.yaml")
    assert "webhook" in action.results.get("Stdout", "")

    # verify keystone pod is running
    await retry_async_with_timeout(
        verify_ready,
        (one_master, "po", ["k8s-keystone-auth"], "-n kube-system"),
        timeout_msg="Unable to find keystone auth pod before timeout",
    )

    skip_tests = False
    action = await one_master.run(
        "cat /snap/cdk-addons/current/templates/keystone-rbac.yaml"
    )
    if "kind: Role" in action.results.get("Stdout", ""):
        # we need to skip tests for the old template that incorrectly had a Role instead
        # of a ClusterRole
        skip_tests = True

    if skip_tests:
        await masters.set_config({"enable-keystone-authorization": "true"})
    else:
        # verify authorization
        await masters.set_config(
            {
                "enable-keystone-authorization": "true",
                "authorization-mode": "Node,Webhook,RBAC",
            }
        )
    await wait_for_process(model, "authorization-webhook-config-file")

    # verify auth fail - bad user
    one_master = random.choice(masters.units)
    await one_master.run("/usr/bin/snap install --edge client-keystone-auth")

    cmd = "source /home/ubuntu/kube-keystone.sh && \
        OS_PROJECT_NAME=k8s OS_DOMAIN_NAME=k8s OS_USERNAME=fake \
        OS_PASSWORD=bad /snap/bin/kubectl --kubeconfig /home/ubuntu/config get clusterroles"
    output = await one_master.run(cmd)
    assert output.status == "completed"
    if (
        "invalid user credentials"
        not in output.data["results"].get("Stderr", "").lower()
    ):
        click.echo("Failing, auth did not fail as expected")
        click.echo(pformat(output.data["results"]))
        assert False

    # verify auth fail - bad password
    cmd = "source /home/ubuntu/kube-keystone.sh && \
        OS_PROJECT_NAME=admin OS_DOMAIN_NAME=admin_domain OS_USERNAME=admin \
        OS_PASSWORD=badpw /snap/bin/kubectl --kubeconfig /home/ubuntu/config get clusterroles"
    output = await one_master.run(cmd)
    assert output.status == "completed"
    if (
        "invalid user credentials"
        not in output.data["results"].get("Stderr", "").lower()
    ):
        click.echo("Failing, auth did not fail as expected")
        click.echo(pformat(output.data["results"]))
        assert False

    if not skip_tests:
        # set up read only access to pods only
        await masters.set_config(
            {
                "keystone-policy": """apiVersion: v1
kind: ConfigMap
metadata:
  name: k8s-auth-policy
  namespace: kube-system
  labels:
    k8s-app: k8s-keystone-auth
data:
  policies: |
    [
      {
        "resource": {
          "verbs": ["get", "list", "watch"],
          "resources": ["pods"],
          "version": "*",
          "namespace": "default"
        },
        "match": [
          {
            "type": "user",
            "values": ["admin"]
          }
        ]
      }
    ]"""
            }
        )
        await tools.juju_wait()

        # verify auth failure on something not a pod
        cmd = f"source /home/ubuntu/kube-keystone.sh && \
            OS_PROJECT_NAME=admin OS_DOMAIN_NAME=admin_domain OS_USERNAME=admin \
            OS_PASSWORD={any_keystone.admin_password} /snap/bin/kubectl \
            --kubeconfig /home/ubuntu/config get clusterroles"
        output = await one_master.run(cmd)
        assert output.status == "completed"
        assert "error" in output.data["results"].get("Stderr", "").lower()

        # the config set writes out a file and updates a configmap, which is then picked up by the
        # keystone pod and updated. This all takes time and I don't know of a great way to tell
        # that it is all done. I could compare the configmap to this, but that doesn't mean the
        # pod has updated. The pod does write a log line about the configmap updating, but
        # I'd need to watch both in succession and it just seems much easier and just as reliable
        # to just retry on failure a few times.

        for i in range(18):  # 3 minutes
            # verify auth success on pods
            cmd = f"source /home/ubuntu/kube-keystone.sh && \
                OS_PROJECT_NAME=admin OS_DOMAIN_NAME=admin_domain OS_USERNAME=admin \
                OS_PASSWORD={any_keystone.admin_password} /snap/bin/kubectl \
                --kubeconfig /home/ubuntu/config get po"
            output = await one_master.run(cmd)
            if (
                output.status == "completed"
                and "invalid user credentials"
                not in output.data["results"].get("Stderr", "").lower()
                and "error" not in output.data["results"].get("Stderr", "").lower()
            ):
                break
            click.echo("Unable to verify configmap change, retrying...")
            await asyncio.sleep(10)

        assert output.status == "completed"
        assert (
            "invalid user credentials"
            not in output.data["results"].get("Stderr", "").lower()
        )
        assert "error" not in output.data["results"].get("Stderr", "").lower()

        # verify auth failure on pods outside of default namespace
        cmd = f"source /home/ubuntu/kube-keystone.sh && \
            OS_PROJECT_NAME=admin OS_DOMAIN_NAME=admin_domain OS_USERNAME=admin \
            OS_PASSWORD={any_keystone.admin_password} /snap/bin/kubectl \
            --kubeconfig /home/ubuntu/config get po -n kube-system"
        output = await one_master.run(cmd)
        assert output.status == "completed"
        assert (
            "invalid user credentials"
            not in output.data["results"].get("Stderr", "").lower()
        )
        assert "forbidden" in output.data["results"].get("Stderr", "").lower()

    # verify auth works now that it is off
    original_auth = config["authorization-mode"]["value"]
    await masters.set_config(
        {
            "enable-keystone-authorization": "false",
            "authorization-mode": original_auth,
        }
    )
    await wait_for_not_process(model, "authorization-webhook-config-file")
    await tools.juju_wait()
    cmd = "/snap/bin/kubectl --context=juju-context \
        --kubeconfig /home/ubuntu/config get clusterroles"
    output = await one_master.run(cmd)
    assert output.status == "completed"
    assert (
        "invalid user credentials"
        not in output.data["results"].get("Stderr", "").lower()
    )
    assert "error" not in output.data["results"].get("Stderr", "").lower()
    assert "forbidden" not in output.data["results"].get("Stderr", "").lower()


@pytest.mark.skip_arch(["aarch64"])
@pytest.mark.on_model("validate-vault")
async def test_encryption_at_rest(model, tools):
    """Testing integrating vault secrets into cluster"""
    master_app = model.applications["kubernetes-control-plane"]
    etcd_app = model.applications["etcd"]
    vault_app = model.applications["vault"]

    async def ensure_vault_up():
        await asyncio.gather(
            *(
                retry_async_with_timeout(vault_status, [unit])
                for unit in vault_app.units
            )
        )

    click.echo("Waiting for Vault to settle")
    await model.wait_for_idle(apps=["vault"], timeout=30 * 60)

    if await vault_app.units[0].is_leader_from_status():
        leader = vault_app.units[0]
    else:
        leader = vault_app.units[1]

    # NB: At this point, depending on the version of the Vault charm, its status
    # might either be (a less than informative) "'etcd' incomplete" (cs:vault-44)
    # or "Vault needs to be initialized" (cs:~openstack-charmers-next/vault).

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
    token_info = await vault(leader, "token create -ttl=10m", VAULT_TOKEN=root_token)
    click.echo(token_info)
    charm_token = token_info["auth"]["client_token"]
    action = await leader.run_action("authorize-charm", token=charm_token)
    await action.wait()
    assert action.status not in ("pending", "running", "failed")

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
    for attempt in range(3):
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
            *(juju_run(unit, "hooks/update-status") for unit in etcd_app.units)
        )

    # Even once etcd is ready, Vault will remain in non-HA mode until the Vault
    # service is restarted, which will re-seal the vault.
    click.echo("Restarting Vault for HA")
    await asyncio.gather(
        *(juju_run(unit, "systemctl restart vault") for unit in vault_app.units)
    )
    await ensure_vault_up()

    click.echo("Unsealing Vault again in HA mode")
    for key in init_info["unseal_keys_hex"][:3]:
        await asyncio.gather(
            *(vault(unit, "operator unseal " + key) for unit in vault_app.units)
        )
    # force unit status to update
    await asyncio.gather(
        *(juju_run(unit, "hooks/update-status") for unit in vault_app.units)
    )
    statuses = sorted(unit.workload_status_message for unit in vault_app.units)
    click.echo(statuses)
    assert statuses == [
        "Unit is ready (active: false, mlock: disabled)",
        "Unit is ready (active: true, mlock: disabled)",
    ]

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

    for attempt in range(3):
        errored_units = [
            unit for unit in master_app.units if unit.workload_status == "error"
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
    await model.wait_for_idle(
        wait_for_active=True, raise_on_blocked=True, timeout=60 * 60
    )

    click.echo("Creating secret")
    await kubectl(
        model,
        "create secret generic test-secret --from-literal=username='secret-value'",
    )

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
        "--endpoints http://127.0.0.1:4001 "
        "get /registry/secrets/default/test-secret | strings",
    )
    assert b64_value not in result.output


@pytest.mark.clouds(["ec2", "vsphere"])
async def test_dns_provider(model, k8s_model, tools):
    master_app = model.applications["kubernetes-control-plane"]
    master_unit = master_app.units[0]

    async def deploy_validation_pod():
        local_path = "jobs/integration/templates/validate-dns-spec.yaml"
        remote_path = "/tmp/validate-dns-spec.yaml"
        await scp_to(
            local_path,
            master_unit,
            remote_path,
            tools.controller_name,
            tools.connection,
        )
        log("Deploying DNS pod")
        await kubectl(model, f"apply -f {remote_path}")
        # wait for pod to be ready (having installed required packages), or failed
        cmd = "logs validate-dns | grep 'validate-dns: \\(Ready\\|Failed\\)'"
        while not (await kubectl(model, cmd, False)).success:
            await asyncio.sleep(5)

    async def remove_validation_pod():
        log("Removing DNS pod")
        await kubectl(model, "delete pod validate-dns --ignore-not-found")

    async def wait_for_pods_ready(label, ns="kube-system"):
        log(f"Waiting for pods with label {label} to be ready")
        cmd = f"get pod -n {ns} -l {label} -o jsonpath='{{.items[*].status.containerStatuses[*].started}}'"
        while result := await kubectl(model, cmd):
            if result.stdout and "false" not in result.stdout:
                break
            await asyncio.sleep(5)

    async def wait_for_pods_removal(label, ns="kube-system", force=False):
        log(f"Waiting for pods with label {label} to be removed")
        cmd = f"get pod -n {ns} -l {label} -o jsonpath='{{.items[*].status.containerStatuses[*].started}}'"
        while result := await kubectl(model, cmd):
            if result.stdout == "":
                break
            if force and ("true" not in result.stdout):
                log("All pods stuck in terminating, forcibly deleting them")
                await kubectl(
                    model, f"delete -n {ns} pod -l {label} --grace-period=0 --force"
                )
                break
            await asyncio.sleep(5)

    async def verify_dns_resolution(*, fresh):
        if fresh:
            await remove_validation_pod()
            await deploy_validation_pod()
        names = ["www.ubuntu.com", "kubernetes.default.svc.cluster.local"]
        for name in names:
            log(f"Checking domain {name}")
            await kubectl(model, f"exec validate-dns -- host {name}")

    async def verify_no_dns_resolution(*, fresh):
        try:
            await verify_dns_resolution(fresh=fresh)
        except AssertionError:
            pass
        else:
            pytest.fail("DNS resolution should not be working with no provider, but is")

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

    # Only run this test against k8s 1.14+
    master_config = await master_app.get_config()
    channel = master_config["channel"]["value"]
    if "/" in channel:
        version_string = channel.split("/")[0]
        k8s_version = tuple(int(q) for q in re.findall("[0-9]+", version_string)[:2])
        if k8s_version < (1, 14):
            click.echo(
                "Skipping validate_dns_provider for k8s version " + version_string
            )
            return

    try:
        log("Verifying DNS with default provider (auto -> coredns)")
        await verify_dns_resolution(fresh=True)

        log("Switching to kube-dns provider")
        await master_app.set_config({"dns-provider": "kube-dns"})
        await wait_for_pods_removal("kubernetes.io/name=CoreDNS")
        await wait_for_pods_ready("k8s-app=kube-dns")

        log("Verifying DNS with kube-dns provider")
        await verify_dns_resolution(fresh=True)

        log("Switching to none provider")
        await master_app.set_config({"dns-provider": "none"})
        # The kube-dns pod gets stuck in Terminating when switching to "none"
        # provider. I think this has something to do with the order (or lack
        # thereof) in which cdk-addons removes the resource types, since it doesn't
        # happen when switching from kube-dns to core-dns. So we force delete them
        # once all their containers are dead.
        await wait_for_pods_removal("k8s-app=kube-dns", force=True)

        log("Verifying DNS no longer works on existing pod")
        await verify_no_dns_resolution(fresh=False)

        log("Verifying DNS no longer works on fresh pod")
        await verify_no_dns_resolution(fresh=True)

        result = await juju_run(master_unit, "cat metadata.yaml")
        master_meta = yaml.safe_load(result.stdout)
        if "dns-provider" not in master_meta["requires"]:
            log("Skipping CoreDNS charm test for older CK")
            return

        log("Deploying CoreDNS charm")
        coredns = await k8s_model.deploy(
            "cs:~containers/coredns",
            channel=tools.charm_channel,
        )

        log("Waiting for CoreDNS charm to be ready")
        while (
            status := coredns.units[0].workload_status if coredns.units else None
        ) != "active":
            assert status not in ("blocked", "error")
            await asyncio.sleep(5)

        log("Creating cross-model offer")
        offer_name = f"{tools.k8s_model_name_full}.coredns"
        await k8s_model.create_offer("coredns:dns-provider")
        try:
            log("Waiting for cross-model offer to be ready")
            while not await get_offer():
                await asyncio.sleep(1)

            log("Consuming cross-model offer")
            await model.consume(offer_name, controller_name=tools.controller_name)

            log("Adding cross-model relation to CK")
            await model.add_relation("kubernetes-control-plane", "coredns")
            await tools.juju_wait()

            log("Verifying that stale pod doesn't pick up new DNS provider")
            await verify_no_dns_resolution(fresh=False)

            log("Verifying DNS works on fresh pod")
            await verify_dns_resolution(fresh=True)
        finally:
            log("Removing cross-model offer")
            if any("coredns" in rel.key for rel in master_app.relations):
                await master_app.destroy_relation("dns-provider", "coredns")
                await tools.juju_wait()
            await model.remove_saas("coredns")
            await k8s_model.remove_offer(offer_name, force=True)
            log("Removing CoreDNS charm")
            # NB: can't use libjuju here because it doesn't support --force.
            await tools.run(
                "juju",
                "remove-application",
                "-m",
                tools.k8s_connection,
                "--force",
                "coredns",
            )
            await wait_for_pods_removal("juju-app=coredns", ns=tools.k8s_model_name)

        log("Verifying that DNS is no longer working")
        await verify_no_dns_resolution(fresh=True)

        log("Switching back to core-dns from cdk-addons")
        await master_app.set_config({"dns-provider": "core-dns"})
        await tools.juju_wait()

        log("Verifying DNS works again")
        await verify_dns_resolution(fresh=True)
    finally:
        # Cleanup
        if (await master_app.get_config())["dns-provider"] != "core-dns":
            await master_app.set_config({"dns-provider": "core-dns"})
            await tools.juju_wait()
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
            action = await unit.run(cmd)
            assert action.status == "completed"
            raw_output = action.data["results"].get("Stdout", "")
            lines = raw_output.splitlines()
            assert len(lines) == len(desired_results)
            if not lines == desired_results:
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


async def test_cloud_node_labels(model, tools):
    unit = model.applications["kubernetes-control-plane"].units[0]
    cmd = "/snap/bin/kubectl --kubeconfig /root/.kube/config get no -o json"
    raw_nodes = await run_until_success(unit, cmd)
    nodes = json.loads(raw_nodes)["items"]
    labels = [node["metadata"].get("labels", {}).get("juju.io/cloud") for node in nodes]
    assert all(label == labels[0] for label in labels)
    label = labels[0]
    if "aws-integrator" in model.applications:
        assert label == "ec2"
    elif "azure-integrator" in model.applications:
        assert label == "azure"
    elif "gcp-integrator" in model.applications:
        assert label == "gce"
    elif "openstack-integrator" in model.applications:
        assert label == "openstack"
    elif "vsphere-integrator" in model.applications:
        assert label == "vsphere"
    else:
        assert label is None


async def test_multus(model, tools, addons_model):
    if "multus" not in addons_model.applications:
        pytest.skip("multus is not deployed")

    unit = model.applications["kubernetes-control-plane"].units[0]
    multus_app = addons_model.applications["multus"]

    async def cleanup():
        await run_until_success(
            unit,
            "/snap/bin/kubectl --kubeconfig /root/.kube/config delete pod multus-test --ignore-not-found",
        )
        await multus_app.set_config({"network-attachment-definitions": ""})

    await cleanup()

    # Create NetworkAttachmentDefinition for Flannel
    net_attach_def = {
        "apiVersion": "k8s.cni.cncf.io/v1",
        "kind": "NetworkAttachmentDefinition",
        "metadata": {"name": "flannel", "namespace": "default"},
        "spec": {
            "config": json.dumps(
                {
                    "cniVersion": "0.3.1",
                    "plugins": [
                        {
                            "type": "flannel",
                            "delegate": {"hairpinMode": True, "isDefaultGateway": True},
                        },
                        {
                            "type": "portmap",
                            "capabilities": {"portMappings": True},
                            "snat": True,
                        },
                    ],
                }
            )
        },
    }
    await multus_app.set_config(
        {"network-attachment-definitions": yaml.safe_dump(net_attach_def)}
    )

    # Create pod with 2 extra flannel interfaces
    pod_definition = {
        "apiVersion": "v1",
        "kind": "Pod",
        "metadata": {
            "name": "multus-test",
            "annotations": {"k8s.v1.cni.cncf.io/networks": "flannel, flannel"},
        },
        "spec": {
            "containers": [
                {
                    "name": "ubuntu",
                    "image": "rocks.canonical.com/cdk/ubuntu:focal",
                    "command": ["sleep", "3600"],
                }
            ]
        },
    }
    remote_path = "/tmp/pod.yaml"
    with NamedTemporaryFile("w") as f:
        yaml.dump(pod_definition, f)
        await scp_to(f.name, unit, remote_path, tools.controller_name, tools.connection)
    await run_until_success(
        unit,
        "/snap/bin/kubectl --kubeconfig /root/.kube/config apply -f " + remote_path,
    )

    # Verify pod has the expected interfaces
    await run_until_success(
        unit,
        "/snap/bin/kubectl --kubeconfig /root/.kube/config exec multus-test -- apt update",
    )
    await run_until_success(
        unit,
        "/snap/bin/kubectl --kubeconfig /root/.kube/config exec multus-test -- apt install -y iproute2",
    )
    output = await run_until_success(
        unit,
        "/snap/bin/kubectl --kubeconfig /root/.kube/config exec multus-test -- ip addr",
    )
    # behold, ugly output parsing :(
    lines = output.splitlines()
    active_interfaces = set()
    while lines:
        line = lines.pop(0)
        interface = line.split()[1].rstrip(":").split("@")[0]
        while lines and lines[0].startswith(" "):
            line = lines.pop(0)
            if line.split()[0] == "inet":
                # interface has an address, we'll call that good enough
                active_interfaces.add(interface)
    expected_interfaces = ["eth0", "net1", "net2"]
    for interface in expected_interfaces:
        if interface not in active_interfaces:
            pytest.fail(
                "Interface %s is missing from ip addr output:\n%s" % (interface, output)
            )

    await cleanup()


def find_nagios_criticals(url, opener):
    url_data = opener.open(url)
    soup = bs(url_data.read(), "html.parser")
    return soup.find_all("td", class_="statusBGCRITICAL")


async def wait_for_no_errors(url, opener):
    criticals = ["dummy"]
    while len(criticals) > 0:
        criticals = find_nagios_criticals(url, opener)
        await asyncio.sleep(30)


async def test_nagios(model, tools):
    """This test verifies the nagios relation is working
    properly. This requires:

    1) Deploy nagios and nrpe
    2) login to nagios
    3) verify things settle and no errors
    4) force api server issues
    5) verify nagios errors show for master and worker
    6) fix api server
    7) break a worker's kubelet
    8) verify nagios errors for worker
    9) fix worker
    """

    log("starting nagios test")
    masters = model.applications["kubernetes-control-plane"]
    k8s_version_str = masters.data["workload-version"]
    k8s_minor_version = tuple(int(i) for i in k8s_version_str.split(".")[:2])
    series = os.environ["SERIES"]
    if series in ("xenial",):
        pytest.skip(f"skipping unsupported series {series}")
    if k8s_minor_version < (1, 17):
        pytest.skip(f"skipping, k8s version v{k8s_version_str}")

    # 1) deploy
    log("deploying nagios and nrpe")
    nagios = await model.deploy("nagios", series="bionic")
    await model.deploy(
        "nrpe", series="bionic", config={"swap": "", "swap_activity": ""}, num_units=0
    )
    await nagios.expose()
    await model.add_relation("nrpe", "kubernetes-control-plane")
    await model.add_relation("nrpe", "kubernetes-worker")
    await model.add_relation("nrpe", "etcd")
    await model.add_relation("nrpe", "easyrsa")
    await model.add_relation("nrpe", "kubeapi-load-balancer")
    await model.add_relation("nagios", "nrpe")
    log("waiting for cluster to settle...")
    await tools.juju_wait()

    # 2) login to nagios
    cmd = "cat /var/lib/juju/nagios.passwd"
    output = await nagios.units[0].run(cmd, timeout=10)
    assert output.status == "completed"
    login_passwd = output.results.get("Stdout", "").strip()

    pwd_mgr = urllib.request.HTTPPasswordMgrWithDefaultRealm()
    url_base = "http://{}".format(nagios.units[0].public_address)
    pwd_mgr.add_password(None, url_base, "nagiosadmin", login_passwd)
    handler = urllib.request.HTTPBasicAuthHandler(pwd_mgr)
    opener = urllib.request.build_opener(handler)
    status_url = "{}/cgi-bin/nagios3/status.cgi?host=all".format(url_base)

    # 3) wait for nagios to settle
    log("waiting for nagios to settle")
    await wait_for_no_errors(status_url, opener)

    # 4) break all the things
    log("breaking api server")
    await masters.set_config({"api-extra-args": "broken=true"})

    # 5) make sure nagios is complaining for kubernetes-control-plane
    #    AND kubernetes-worker
    log("Verifying complaints")
    criticals = []
    while True:
        criticals = find_nagios_criticals(status_url, opener)

        if criticals:
            found_master = []
            found_worker = []
            for c in criticals:
                for link in c.find_all("a", recursive=False):
                    if "kubernetes-control-plane" in link.string:
                        found_master.append(link.string)
                    elif "kubernetes-worker" in link.string:
                        found_worker.append(link.string)
            if found_master and found_worker:
                log("Found critical errors:")
                for s in found_master + found_worker:
                    log(" - {}".format(s))
                break
        await asyncio.sleep(30)

    # 6) fix api and wait for settle
    log("Fixing API server")
    await masters.set_config({"api-extra-args": ""})
    await wait_for_no_errors(status_url, opener)

    # 7) break worker
    log("Breaking workers")
    workers = masters = model.applications["kubernetes-worker"]
    await workers.set_config({"kubelet-extra-args": "broken=true"})

    # 8) verify nagios is complaining about worker
    log("Verifying complaints")
    criticals = []
    while True:
        criticals = find_nagios_criticals(status_url, opener)

        if criticals:
            found_worker = []
            for c in criticals:
                for link in c.find_all("a", recursive=False):
                    if "kubernetes-worker" in link.string:
                        found_worker.append(link.string)
                        break
            if found_worker:
                log("Found critical errors:")
                for s in found_worker:
                    log(" - {}".format(s))
                break
        await asyncio.sleep(30)

    # 9) Fix worker and wait for complaints to go away
    await workers.set_config({"kubelet-extra-args": ""})
    await wait_for_no_errors(status_url, opener)


@pytest.mark.skip("Failing and being investigated on possible deprecation")
async def test_nfs(model, tools):
    # setup
    log("deploying nfs")
    await model.deploy("nfs")

    log("adding relations")
    await model.add_relation("nfs", "kubernetes-worker")
    log("waiting...")
    await tools.juju_wait()

    log("waiting for nfs pod to settle")
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


async def test_ceph(model, tools):
    # setup
    series = os.environ["SERIES"]
    if series == "xenial":
        pytest.skip("Ceph not supported fully on xenial")
    snap_ver = os.environ["SNAP_VERSION"].split("/")[0]
    check_cephfs = snap_ver not in ("1.15", "1.16")
    ceph_config = {}
    if check_cephfs and series == "bionic":
        log("adding cloud:train to k8s-control-plane")
        await model.applications["kubernetes-control-plane"].set_config(
            {"install_sources": "[cloud:{}-train]".format(series)}
        )
        await tools.juju_wait()
        ceph_config["source"] = "cloud:{}-train".format(series)
    log("deploying ceph mon")
    await model.deploy(
        "ceph-mon",
        num_units=3,
        series=series,
        config=ceph_config,
    )
    cs = {
        "osd-devices": {"size": 8 * 1024, "count": 1},
        "osd-journals": {"size": 8 * 1024, "count": 1},
    }
    log("deploying ceph osd")
    await model.deploy(
        "ceph-osd",
        storage=cs,
        num_units=3,
        series=series,
        config=ceph_config,
        constraints="root-disk=32G",
    )
    if check_cephfs:
        log("deploying ceph fs")
        await model.deploy(
            "ceph-fs",
            num_units=1,
            series=series,
            config=ceph_config,
        )

    log("adding relations")
    await model.add_relation("ceph-mon", "ceph-osd")
    if check_cephfs:
        await model.add_relation("ceph-mon", "ceph-fs")
    await model.add_relation("ceph-mon:admin", "kubernetes-control-plane")
    await model.add_relation("ceph-mon:client", "kubernetes-control-plane")
    log("waiting...")
    await tools.juju_wait()

    # until bug https://bugs.launchpad.net/charm-kubernetes-control-plane/+bug/1824035 fixed
    unit = model.applications["ceph-mon"].units[0]
    action = await unit.run_action("create-pool", name="ext4-pool")
    await action.wait()
    assert action.status == "completed"

    log("waiting for csi to settle")
    unit = model.applications["kubernetes-control-plane"].units[0]
    await retry_async_with_timeout(
        verify_ready, (unit, "po", ["csi-rbdplugin"]), timeout_msg="CSI pods not ready!"
    )
    # create pod that writes to a pv from ceph
    await validate_storage_class(model, "ceph-xfs", "Ceph")
    await validate_storage_class(model, "ceph-ext4", "Ceph")
    if check_cephfs:
        await validate_storage_class(model, "cephfs", "Ceph")
    # cleanup
    log("removing ceph applications")
    tasks = {
        model.applications["ceph-mon"].destroy(),
        model.applications["ceph-osd"].destroy(),
    }
    if check_cephfs:
        tasks.add(model.applications["ceph-fs"].destroy())
    (done1, pending1) = await asyncio.wait(tasks)
    for task in done1:
        # read and ignore any exception so that it doesn't get raised
        # when the task is GC'd
        task.exception()
    await tools.juju_wait()


async def test_series_upgrade(model, tools):
    if not tools.is_series_upgrade:
        pytest.skip("No series upgrade argument found")
    k8s_master_0 = model.applications["kubernetes-control-plane"].units[0]
    old_series = k8s_master_0.machine.series
    try:
        new_series = SERIES_ORDER[SERIES_ORDER.index(old_series) + 1]
    except IndexError:
        pytest.skip("no supported series to upgrade to")
    except ValueError:
        pytest.skip("unrecognized series to upgrade from: {old_series}")
    for machine in model.machines.values():
        await prep_series_upgrade(machine, new_series, tools)
        await do_series_upgrade(machine)
        await finish_series_upgrade(machine, tools)
        assert machine.series == new_series
    expected_messages = {
        "kubernetes-control-plane": "Kubernetes master running.",
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
async def test_octavia(model, tools):
    assert "openstack-integrator" in model.applications, "Missing integrator"
    log("Deploying microbot")
    unit = model.applications["kubernetes-worker"].units[0]
    action = await unit.run_action("microbot", delete=True)
    await action.wait()
    action = await unit.run_action("microbot", replicas=3)
    await action.wait()
    assert action.status == "completed"
    try:
        log("Replacing microbot service with Octavia LB")
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
        resp = await tools.requests.get(
            f"http://{ingress_address}",
            proxies={"http": None, "https": None},
        )
        assert resp.status_code == 200
    finally:
        # cleanup
        action = await unit.run_action("microbot", delete=True)
        await action.wait()


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
    await tools.juju_wait("-x", "kubernetes-worker")
    # Block until containerd's removed, ignore `blocked` worker.

    docker_app = await model.deploy(
        "cs:~containers/docker", num_units=0, channel="edge"  # Subordinate.
    )

    await docker_app.add_relation("docker", "kubernetes-control-plane")

    await docker_app.add_relation("docker", "kubernetes-worker")

    await tools.juju_wait()
    # If we settle, it's safe to
    # assume Docker is now running
    # workloads.

    await docker_app.remove()
    await tools.juju_wait("-x", "kubernetes-worker")
    # Block until docker's removed, ignore `blocked` worker.

    containerd_app = await model.deploy(
        "cs:~containers/containerd", num_units=0, channel="edge"  # Subordinate.
    )

    await containerd_app.add_relation("containerd", "kubernetes-control-plane")

    await containerd_app.add_relation("containerd", "kubernetes-worker")

    await tools.juju_wait()


async def test_sriov_cni(model, tools, addons_model):
    if "sriov-cni" not in addons_model.applications:
        pytest.skip("sriov-cni is not deployed")

    for unit in model.applications["kubernetes-worker"].units:
        action = await unit.run("[ -x /opt/cni/bin/sriov ]")
        assert action.status == "completed"
        assert action.data["results"]["Code"] == "0"


async def test_sriov_network_device_plugin(model, tools, addons_model):
    if "sriov-network-device-plugin" not in addons_model.applications:
        pytest.skip("sriov-network-device-plugin is not deployed")

    app = addons_model.applications["sriov-network-device-plugin"]
    config = await app.get_config()
    resource_list = yaml.load(config["resource-list"]["value"])
    resource_prefix = config["resource-prefix"]["value"]
    resource_names = [
        resource_prefix + "/" + resource["resourceName"] for resource in resource_list
    ]

    master_unit = model.applications["kubernetes-control-plane"].units[0]
    cmd = "/snap/bin/kubectl --kubeconfig /root/.kube/config get node -o json"
    raw_output = await run_until_success(master_unit, cmd)
    data = json.loads(raw_output)
    for node in data["items"]:
        capacity = node["status"]["capacity"]
        for resource_name in resource_names:
            assert resource_name in capacity
