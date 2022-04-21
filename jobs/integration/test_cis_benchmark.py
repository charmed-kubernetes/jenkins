import random
from .logger import log


async def test_cis_benchmark(model, tools):
    """Validate cis benchmark passes on supported charms in 1.19+"""
    log("starting cis-benchmark test")
    masters = model.applications["kubernetes-control-plane"]
    k8s_version_str = masters.data["workload-version"]
    k8s_minor_version = tuple(int(i) for i in k8s_version_str.split(".")[:2])
    if k8s_minor_version < (1, 19):
        log("skipping, k8s version v" + k8s_version_str)
        return

    # Verify action on etcd
    log("verifying etcd")
    etcds = model.applications["etcd"]
    one_etcd = random.choice(etcds.units)
    action = await one_etcd.run_action("cis-benchmark")
    await action.wait()
    assert action.status == "completed"
    assert "0 checks FAIL" in action.data["results"]["summary"]

    # Verify action on k8s-master
    log("verifying k8s-master")
    one_master = random.choice(masters.units)
    action = await one_master.run_action("cis-benchmark")
    await action.wait()
    assert action.status == "completed"
    assert "0 checks FAIL" in action.data["results"]["summary"]

    # Verify action on k8s-worker
    log("verifying k8s-worker")
    workers = model.applications["kubernetes-worker"]
    one_worker = random.choice(workers.units)
    action = await one_worker.run_action("cis-benchmark")
    await action.wait()
    assert action.status == "completed"
    assert "0 checks FAIL" in action.data["results"]["summary"]
