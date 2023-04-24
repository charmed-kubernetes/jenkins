import random
from utils import juju_run_action
from .logger import log


@pytest.mark.skip_if_version(lambda v: v < (1, 19))
async def test_cis_benchmark(model, tools):
    """Validate cis benchmark passes on supported charms in 1.19+"""
    log("starting cis-benchmark test")
    masters = model.applications["kubernetes-control-plane"]

    # Verify action on etcd
    log("verifying etcd")
    etcds = model.applications["etcd"]
    one_etcd = random.choice(etcds.units)
    action = await juju_run_action(one_etcd, "cis-benchmark")
    assert "0 checks FAIL" in action.results["summary"]

    # Verify action on k8s-master
    log("verifying k8s-master")
    one_master = random.choice(masters.units)
    action = await juju_run_action(one_master, "cis-benchmark")
    assert "0 checks FAIL" in action.results["summary"]

    # Verify action on k8s-worker
    log("verifying k8s-worker")
    workers = model.applications["kubernetes-worker"]
    one_worker = random.choice(workers.units)
    action = await juju_run_action(one_worker, "cis-benchmark")
    assert "0 checks FAIL" in action.results["summary"]
