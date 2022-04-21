import asyncio
import random
import os
from .logger import log


def get_test_ips():
    env = os.environ.get("TEST_IPS")
    if env:
        return env.split()
    else:
        # default to some randomish scapestack IPs
        return ["10.96.117.5", "10.96.117.200"]


def get_master_name(model):
    if "kubeapi-load-balancer" in model.applications:
        return "kubeapi-load-balancer"
    else:
        return "kubernetes-control-plane"


def is_app_in_model(app_str, model):
    """Searches for app names in the juju model containing app_str."""
    for app in model.applications.keys():
        if app_str in app:
            return True
    return False


async def verify_kubeconfig_has_ip(model, ip):
    log("validating generated kubectl config file")
    one_master = random.choice(model.applications["kubernetes-control-plane"].units)
    for i in range(5):
        action = await one_master.run("cat /home/ubuntu/config")
        if ip in action.results.get("Stdout", ""):
            break
        log("Unable to find virtual IP information in kubeconfig, retrying...")
        await asyncio.sleep(10)
    assert ip in action.results.get("Stdout", "")


async def verify_kubelet_uses_ip(model, ip):
    log("validating generated kubelet config files")
    for worker_unit in model.applications["kubernetes-worker"].units:
        cmd = "cat /root/cdk/kubeconfig"
        for i in range(5):
            action = await worker_unit.run(cmd)
            if ip in action.results.get("Stdout", ""):
                break
            log("Unable to find virtual IP" "information in kubeconfig, retrying...")
            await asyncio.sleep(10)
        assert ip in action.results.get("Stdout", "")


async def verify_ip_valid(model, ip):
    log("validating ip {} is pingable".format(ip))
    cmd = "ping -c 1 {}".format(ip)
    one_master = random.choice(model.applications["kubernetes-control-plane"].units)
    one_worker = random.choice(model.applications["kubernetes-worker"].units)
    for unit in [one_master, one_worker]:
        action = await unit.run(cmd)
        assert ", 0% packet loss" in action.results.get("Stdout", "")


async def do_verification(model, app, ip):
    """Basic hacluster verification

    Verifies:
      corosync and pacemaker
      kubeconfig and kubelet config point to vip
      VIP is pingable
    """
    log("verifying corosync...")
    for unit in app.units:
        action = await unit.run("corosync-cmapctl")
        assert "runtime.totem.pg.mrp.srp.members" in action.results.get("Stdout", "")

    log("verifying pacemaker...")
    for unit in app.units:
        action = await unit.run("crm status")
        assert "Stopped" not in action.results.get("Stdout", "")

    # kubeconfig points to virtual ip
    await verify_kubeconfig_has_ip(model, ip)
    # kubelet config points to virtual ip
    await verify_kubelet_uses_ip(model, ip)
    # virtual ip is pingable
    await verify_ip_valid(model, ip)


async def test_validate_existing_hacluster(model, tools):
    """Assume hacluster is already set up and do not modify the deploy"""
    name = get_master_name(model)
    app = model.applications[name]

    for ip in get_test_ips():
        await do_verification(model, app, ip)


async def test_validate_hacluster(model, tools):
    name = get_master_name(model)
    app = model.applications[name]

    masters = model.applications["kubernetes-control-plane"]
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

    if not is_app_in_model("hacluster", model):
        log("deploying hacluster...")
        await model.deploy("hacluster", num_units=0, series="bionic")
        await model.add_relation("hacluster:ha", "{}:ha".format(name))
        log("waiting for cluster to settle...")
        await tools.juju_wait()

    # virtual ip can change, verify that
    for ip in get_test_ips():
        cfg = {"ha-cluster-vip": ip, "ha-cluster-dns": ""}
        log("using ip {}".format(ip))
        await app.set_config(cfg)

        log("waiting for cluster to settle...")
        await tools.juju_wait()

        await do_verification(model, app, ip)
