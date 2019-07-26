import asyncio
import pytest
from .utils import (
    _juju_wait,
    asyncify,
    verify_ready,
    verify_completed,
    verify_deleted,
    retry_async_with_timeout,
)
from .logger import log


async def validate_storage_class(model, sc_name):
    master = model.applications["kubernetes-master"].units[0]
    # write a string to a file on the pvc
    pod_definition = """
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: {0}-pvc
  annotations:
   volume.beta.kubernetes.io/storage-class: {0}
spec:
  accessModes:
  - ReadWriteOnce
  resources:
    requests:
      storage: 1Gi
---
kind: Pod
apiVersion: v1
metadata:
  name: {0}-write-test
spec:
  volumes:
  - name: shared-data
    persistentVolumeClaim:
      claimName: {0}-pvc
      readOnly: false
  containers:
    - name: {0}-write-test
      image: ubuntu
      command: ["/bin/bash", "-c", "echo 'JUJU TEST' > /data/juju"]
      volumeMounts:
      - name: shared-data
        mountPath: /data
  restartPolicy: Never
""".format(
        sc_name
    )
    cmd = "/snap/bin/kubectl create -f - << EOF{}EOF".format(pod_definition)
    log("Ceph: {} writing test".format(sc_name))
    output = await master.run(cmd)
    assert output.status == "completed"

    # wait for completion
    await retry_async_with_timeout(
        verify_completed,
        (master, "po", ["{}-write-test".format(sc_name)]),
        timeout_msg="Unable to create write" " pod for ceph test",
    )

    # read that string from ceph pvc
    pod_definition = """
kind: Pod
apiVersion: v1
metadata:
  name: {0}-read-test
spec:
  volumes:
  - name: shared-data
    persistentVolumeClaim:
      claimName: {0}-pvc
      readOnly: false
  containers:
    - name: {0}-read-test
      image: ubuntu
      command: ["/bin/bash", "-c", "cat /data/juju"]
      volumeMounts:
      - name: shared-data
        mountPath: /data
  restartPolicy: Never
""".format(
        sc_name
    )
    cmd = "/snap/bin/kubectl create -f - << EOF{}EOF".format(pod_definition)
    log("Ceph: {} reading test".format(sc_name))
    output = await master.run(cmd)
    assert output.status == "completed"

    # wait for completion
    await retry_async_with_timeout(
        verify_completed,
        (master, "po", ["{}-read-test".format(sc_name)]),
        timeout_msg="Unable to create write" " pod for ceph test",
    )

    output = await master.run("/snap/bin/kubectl logs {}-read-test".format(sc_name))
    assert output.status == "completed"
    log("output = {}".format(output.data["results"]["Stdout"]))
    assert "JUJU TEST" in output.data["results"]["Stdout"]

    log("Ceph: {} cleanup".format(sc_name))
    pods = "{0}-read-test {0}-write-test".format(sc_name)
    pvcs = "{}-pvc".format(sc_name)
    output = await master.run("/snap/bin/kubectl delete po {}".format(pods))
    assert output.status == "completed"
    output = await master.run("/snap/bin/kubectl delete pvc {}".format(pvcs))
    assert output.status == "completed"

    await retry_async_with_timeout(
        verify_deleted,
        (master, "po", pods),
        timeout_msg="Unable to remove" " the ceph test pods",
    )
    await retry_async_with_timeout(
        verify_deleted,
        (master, "pvc", pvcs),
        timeout_msg="Unable to remove" " the ceph test pvc",
    )


@pytest.mark.asyncio
async def test_ceph(model):
    # setup
    log("deploying ceph mon")
    await model.deploy("ceph-mon", num_units=3)
    cs = {
        "osd-devices": {"size": 8 * 1024, "count": 1},
        "osd-journals": {"size": 8 * 1024, "count": 1},
    }
    log("deploying ceph osd")
    await model.deploy("ceph-osd", storage=cs, num_units=3)

    log("adding relations")
    await model.add_relation("ceph-mon", "ceph-osd")
    await model.add_relation("ceph-mon:admin", "kubernetes-master")
    await model.add_relation("ceph-mon:client", "kubernetes-master")
    log("waiting...")
    await asyncify(_juju_wait)()

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
    await validate_storage_class(model, "ceph-xfs")
    await validate_storage_class(model, "ceph-ext4")
    # cleanup
    (done1, pending1) = await asyncio.wait(
        {
            model.applications["ceph-mon"].destroy(),
            model.applications["ceph-osd"].destroy(),
        }
    )
    for task in done1:
        # read and ignore any exception so that it doesn't get raised
        # when the task is GC'd
        task.exception()
