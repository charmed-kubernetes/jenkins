import asyncio
import pytest
import random
import os
from .utils import asyncify, _juju_wait
from .logger import log


def get_test_ips():
    env = os.environ.get("TEST_IPS")
    if env:
        return env.split()
    else:
        # default to some randomish scapestack IPs
        return ["10.96.117.5", "10.96.117.200"]


async def verify_kubeconfig_has_ip(model, ip):
    log("validating generated kubectl config file")
    one_master = random.choice(model.applications["kubernetes-master"].units)
    for i in range(5):
        action = await one_master.run("cat /home/ubuntu/config")
        if ip in action.results["Stdout"]:
            break
        log("Unable to find virtual IP information in kubeconfig, retrying...")
        await asyncio.sleep(10)
    assert ip in action.results["Stdout"]


async def verify_kubelet_uses_ip(model, ip):
    log("validating generated kubelet config files")
    for worker_unit in model.applications["kubernetes-worker"].units:
        cmd = "cat /root/cdk/kubeconfig"
        for i in range(5):
            action = await worker_unit.run(cmd)
            if ip in action.results["Stdout"]:
                break
            log("Unable to find virtual IP" "information in kubeconfig, retrying...")
            await asyncio.sleep(10)
        assert ip in action.results["Stdout"]


async def verify_ip_valid(model, ip):
    log("validating ip {} is pingable".format(ip))
    cmd = "ping -c 1 {}".format(ip)
    one_master = random.choice(model.applications["kubernetes-master"].units)
    one_worker = random.choice(model.applications["kubernetes-worker"].units)
    for unit in [one_master, one_worker]:
        action = await unit.run(cmd)
        assert ", 0% packet loss" in action.results["Stdout"]


@pytest.mark.asyncio
async def test_validate_hacluster(model):
    if "kubeapi-load-balancer" in model.applications:
        name = "kubeapi-load-balancer"
        app = model.applications[name]
    else:
        name = "kubernetes-master"
        app = model.applications[name]

    masters = model.applications["kubernetes-master"]
    k8s_version_str = masters.data["workload-version"]
    k8s_minor_version = tuple(int(i) for i in k8s_version_str.split(".")[:2])
    if k8s_minor_version < (1, 14):
        log("skipping, k8s version v" + k8s_version_str)
        # return

    num_units = len(app.units)
    if num_units < 3:
        msg = "adding {} units to {} in order to support hacluster"
        log(msg.format(3 - num_units, name))
        await app.add_unit(3 - num_units)

    # ensure no vip/dns set
    await app.set_config({"ha-cluster-vip": "", "ha-cluster-dns": ""})

    log("deploying hacluster...")
    await model.deploy("hacluster", num_units=0, series="bionic")
    await model.add_relation("hacluster:ha", "{}:ha".format(name))
    log("waiting for cluster to settle...")
    await asyncify(_juju_wait)()

    # virtual ip can change, verify that
    for ip in get_test_ips():
        cfg = {"ha-cluster-vip": ip, "ha-cluster-dns": ""}
        log("using ip {}".format(ip))
        await app.set_config(cfg)

        log("waiting for cluster to settle...")
        await asyncify(_juju_wait)()

        # tests:
        log("verifying corosync...")
        for unit in app.units:
            action = await unit.run("corosync-cmapctl")
            assert "runtime.totem.pg.mrp.srp.members" in action.results["Stdout"]

        log("verifying pacemaker...")
        for unit in app.units:
            action = await unit.run("crm status")
            assert "Stopped" not in action.results["Stdout"]

        # kubeconfig points to virtual ip
        await verify_kubeconfig_has_ip(model, ip)
        # kubelet config points to virtual ip
        await verify_kubelet_uses_ip(model, ip)
        # virtual ip is pingable
        await verify_ip_valid(model, ip)
