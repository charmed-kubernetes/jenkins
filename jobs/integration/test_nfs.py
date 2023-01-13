from .utils import verify_ready, retry_async_with_timeout, validate_storage_class
from .logger import log


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
