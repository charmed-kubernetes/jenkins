import asyncio
import pytest
from .utils import verify_ready, retry_async_with_timeout, validate_storage_class
from .logger import log


@pytest.mark.asyncio
async def test_ceph(model, tools):
    # setup
    log("adding cloud:train to k8s-master")
    await model.applications['kubernetes-master'].set_config({
        'install_sources': '[cloud:train]',
    })
    await tools.juju_wait()
    log("deploying ceph mon")
    await model.deploy("ceph-mon", num_units=3, config={'source': 'cloud:train'})
    cs = {
        "osd-devices": {"size": 8 * 1024, "count": 1},
        "osd-journals": {"size": 8 * 1024, "count": 1},
    }
    log("deploying ceph osd")
    await model.deploy("ceph-osd", storage=cs, num_units=3, config={'source': 'cloud:train'})
    log("deploying ceph fs")
    await model.deploy("ceph-fs", num_units=1, config={'source': 'cloud:train'})

    log("adding relations")
    await model.add_relation("ceph-mon", "ceph-osd")
    await model.add_relation("ceph-mon", "ceph-fs")
    await model.add_relation("ceph-mon:admin", "kubernetes-master")
    await model.add_relation("ceph-mon:client", "kubernetes-master")
    log("waiting...")
    await tools.juju_wait()

    # until bug https://bugs.launchpad.net/charm-kubernetes-master/+bug/1824035 fixed
    unit = model.applications["ceph-mon"].units[0]
    action = await unit.run_action("create-pool", name="ext4-pool")
    await action.wait()
    assert action.status == "completed"

    log("waiting for csi to settle")
    unit = model.applications["kubernetes-master"].units[0]
    await retry_async_with_timeout(
        verify_ready, (unit, "po", ["csi-rbdplugin"]), timeout_msg="CSI pods not ready!"
    )
    # create pod that writes to a pv from ceph
    await validate_storage_class(model, "ceph-xfs", "Ceph")
    await validate_storage_class(model, "ceph-ext4", "Ceph")
    await validate_storage_class(model, "cephfs", "Ceph")
    # cleanup
    (done1, pending1) = await asyncio.wait(
        {
            model.applications["ceph-mon"].destroy(),
            model.applications["ceph-osd"].destroy(),
            model.applications["ceph-fs"].destroy(),
        }
    )
    for task in done1:
        # read and ignore any exception so that it doesn't get raised
        # when the task is GC'd
        task.exception()
