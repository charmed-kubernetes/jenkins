import asyncio
import logging
import pytest
import re
from pathlib import Path
from ..utils import juju_run, juju_run_action

ws_logger = logging.getLogger("websockets.protocol")
ws_logger.setLevel(logging.INFO)


async def test_etcd_actions(model, tools):
    """Test etcd charm actions"""

    async def assert_action(unit, action, output_regex=None, **action_params):
        action = await juju_run_action(unit, action, **action_params)
        if output_regex:
            output = action.results["output"]
            assert re.search(output_regex, output)

    etcd = model.applications["etcd"].units[0]
    # set db size limit to 16MB so we can fill it quickly
    await juju_run(
        etcd,
        "sed -i 's/^quota-backend-bytes:.*$/quota-backend-bytes: 16777216/' /var/snap/etcd/common/etcd.conf.yml",
    )
    await juju_run(etcd, "sudo systemctl restart snap.etcd.etcd.service")
    # fill the db to cause an alarm
    await juju_run(
        etcd,
        "while [ 1 ]; do dd if=/dev/urandom bs=1024 count=1024 | ETCDCTL_API=3 /snap/bin/etcd.etcdctl --endpoints :4001 put key || break; done",
    )

    # confirm alarm is raised
    await assert_action(etcd, "alarm-list", r"alarm:NOSPACE")
    # compact and defrag db, then disarm alarm
    await assert_action(etcd, "compact", r"compacted revision", physical=True)
    await assert_action(etcd, "defrag", r"Finished defragmenting")
    await assert_action(etcd, "alarm-disarm")
    # confirm alarm is gone
    await assert_action(etcd, "alarm-list", r"^$")

    # reset db size to unlimited (default)
    await juju_run(
        etcd,
        "sed -i 's/^quota-backend-bytes:.*$/quota-backend-bytes: 0/' /var/snap/etcd/common/etcd.conf.yml",
    )
    await juju_run(etcd, "sudo systemctl restart snap.etcd.etcd.service")


async def test_etcd_scaling(model, tools):
    """Scale etcd up and down and ensure the cluster state remains healthy."""
    e = asyncio.Event()

    async def on_unit_removed(delta, old_obj, new_obj, model):
        e.set()

    etcd = model.applications["etcd"]

    # Scale down
    for unit in etcd.units:
        is_leader = await unit.is_leader_from_status()
        if is_leader:
            unit.on_remove(on_unit_removed)
            await etcd.destroy_unit(unit.name)
            await e.wait()
            break
    await tools.juju_wait()
    await test_cluster_health(model, tools)

    # Scale up
    await etcd.add_units(count=1)
    await tools.juju_wait()
    await test_cluster_health(model, tools)


@pytest.mark.skip("Need to manually verify result tarball")
async def test_snapshot_restore(model, tools):
    """
    Trigger snapshot and restore actions
    """
    from sh import juju, ls

    etcd = model.applications["etcd"]
    for unit in etcd.units:
        leader = await unit.is_leader_from_status()
        if leader:
            # Load dummy data
            await load_data(unit)
            for ver in ["v3"]:
                assert await is_data_present(unit, ver)
            filenames = {}
            for dataset in ["v3"]:
                # Take snapshot of data
                action = await juju_run_action(
                    unit, "snapshot", **{"keys-version": dataset}
                )
                src = Path(action.results["snapshot"]["path"])
                dst = Path(action.results["snapshot"]["path"]).name
                await unit.scp_from(
                    str(src),
                    str(dst),
                    tools.controller_name,
                    tools.connection,
                    proxy=tools.juju_ssh_proxy,
                )
                filenames[dataset] = str(dst)
                out = ls("-l", "result*")
                print(out.stdout.decode().strip())

            await delete_data(unit)
            for ver in ["v3"]:
                assert await is_data_present(unit, ver) is False

            # Restore v2 data
            # Note: libjuju does not implement attach yet.
            juju(
                "attach",
                "-m",
                "{}:{}".format(tools.controller_name, model.info.name),
                "etcd",
                "snapshot='./{}'".format(str(filenames["v2"])),
            )
            action = await juju_run_action(unit, "restore")
            for ver in ["v3"]:
                assert await is_data_present(unit, ver) is True

            # Restore v3 data
            juju(
                "attach",
                "-m",
                "{}:{}".format(tools.controller_name, model.info.name),
                "etcd",
                "snapshot='./{}'".format(str(filenames["v3"])),
            )

            action = await juju_run_action(unit, "restore")
            for ver in ["v3"]:
                assert await is_data_present(unit, ver) is True


async def test_leader_status(model, tools):
    """Verify our leader is running the etcd daemon"""
    etcd = model.applications["etcd"]
    for unit in etcd.units:
        is_leader = await unit.is_leader_from_status()
        if is_leader:
            status = await juju_run(
                unit, "systemctl is-active snap.etcd.etcd", check=False
            )
            assert "inactive" not in status.stdout.strip()
            assert "active" in status.stdout.strip()


async def test_config_snapd_refresh(model, tools):
    """Verify initial snap refresh config is set and can be changed"""
    etcd = model.applications["etcd"]
    for unit in etcd.units:
        is_leader = await unit.is_leader_from_status()
        if is_leader:
            # default timer should be some day of the week followed by a
            # number
            timer = await juju_run(unit, "snap get core refresh.timer")
            assert len(timer.stdout.strip()) == len("dayX")

            # verify a new timer value
            await etcd.set_config({"snapd_refresh": "fri5"})
            timer = await juju_run(unit, "snap get core refresh.timer")
            assert timer.stdout.strip() == "fri5"


async def test_cluster_health(model, tools):
    """Iterate all the units and verify we have a clean bill of health
    from etcd"""
    certs = (
        "ETCDCTL_KEY_FILE=/var/snap/etcd/common/client.key "
        "ETCDCTL_CERT_FILE=/var/snap/etcd/common/client.crt "
        "ETCDCTL_CA_FILE=/var/snap/etcd/common/ca.crt"
    )

    etcd = model.applications["etcd"]
    for unit in etcd.units:
        out = await juju_run(unit, "systemctl is-active snap.etcd.etcd")
        assert "inactive" not in out.stdout.strip()
        assert "active" in out.stdout.strip()
        cmd = "{} /snap/bin/etcdctl cluster-health".format(certs)
        health = await juju_run(unit, cmd)
        assert "unhealthy" not in health.stdout.strip()
        assert "unavailable" not in health.stdout.strip()


async def test_leader_knows_all_members(model, tools):
    """Test we have the same number of units deployed and reporting in
    the etcd cluster as participating"""

    # The spacing here is semi-important as its a string of ENV exports
    # also, this is hard coding for the defaults. if the defaults in
    # layer.yaml change, this will need to change.
    certs = (
        "ETCDCTL_KEY_FILE=/var/snap/etcd/common/client.key "
        "ETCDCTL_CERT_FILE=/var/snap/etcd/common/client.crt "
        "ETCDCTL_CA_FILE=/var/snap/etcd/common/ca.crt"
    )

    # format the command, and execute on the leader
    cmd = "{} ETCDCTL_API=2 /snap/bin/etcd.etcdctl member list".format(certs)

    etcd = model.applications["etcd"]
    for unit in etcd.units:
        is_leader = await unit.is_leader_from_status()
        if is_leader:
            out = await juju_run(unit, cmd)
            # turn the output into a list so we can iterate
            members = out.stdout.strip()
            members = members.split("\n")
            for item in members:
                # this is responded when TLS is enabled and we don't have
                # proper Keys. This is kind of a "ssl works test" but of
                # the worse variety... assuming the full stack completed.
                assert "etcd cluster is unavailable" not in members
            assert len(members) == len(etcd.units)


# TODO: Can we remove these?
# async def validate_etcd_fixture_data(etcd):
#     """ Recall data set by set_etcd_fixture_data to ensure it persisted
#     through the upgrade """

#     # The spacing here is semi-important as its a string of ENV exports
#     # also, this is hard coding for the defaults. if the defaults in
#     # layer.yaml change, this will need to change.
#     certs = (
#         "ETCDCTL_KEY_FILE=/var/snap/etcd/common/client.key "
#         "ETCDCTL_CERT_FILE=/var/snap/etcd/common/client.crt "
#         "ETCDCTL_CA_FILE=/var/snap/etcd/common/ca.crt"
#     )

#     etcd = model.applications["etcd"]
#     for unit in etcd.units:
#         is_leader = await unit.is_leader_from_status()
#         if is_leader:
#             await juju_run(unit, "{} /snap/bin/etcd.etcdctl set juju rocks".format(certs))
#             await juju_run(unit,
#                 "{} /snap/bin/etcd.etcdctl set nested/data works".format(certs)
#             )

#             juju_key = await juju_run(unit,
#                 "{} /snap/bin/etcd.etcdctl get juju rocks".format(certs)
#             )
#             nested_key = await juju_run(unit,
#                 "{} /snap/bin/etcd.etcdctl get nested/data works".format(certs)
#             )

#             assert "rocks" in juju_key.stdout.strip()
#             assert "works" in nested_key.stdout.strip()


# async def validate_running_snap_daemon(etcd):
#     """ Validate the snap based etcd daemon is running after an op """
#     etcd = model.applications["etcd"]
#     for unit in etcd.units:
#         is_leader = await unit.is_leader_from_status()
#         if is_leader:
#             daemon_status = await juju_run(unit, "systemctl is-active snap.etcd.etcd")
#             assert "active" in daemon_status.stdout.strip()


async def load_data(leader):
    """
    Load dummy data

    """
    certs = (
        "ETCDCTL_KEY_FILE=/var/snap/etcd/common/client.key "
        "ETCDCTL_CERT_FILE=/var/snap/etcd/common/client.crt "
        "ETCDCTL_CA_FILE=/var/snap/etcd/common/ca.crt"
    )

    cmd = "{} ETCDCTL_API=2 /snap/bin/etcd.etcdctl set /etcd2key etcd2value".format(
        certs
    )
    await juju_run(leader, cmd)
    cmd = (
        "{} ETCDCTL_API=3 /snap/bin/etcd.etcdctl --endpoints=http://localhost:4001 "
        "put etcd3key etcd3value".format(certs)
    )
    await juju_run(leader, cmd)


async def is_data_present(leader, version):
    """
    Check if we have the data present on the datastore of the version
    Args:
        version: v2 or v3 etcd datastore

    Returns: True if the data is present

    """
    certs = (
        "ETCDCTL_KEY_FILE=/var/snap/etcd/common/client.key "
        "ETCDCTL_CERT_FILE=/var/snap/etcd/common/client.crt "
        "ETCDCTL_CA_FILE=/var/snap/etcd/common/ca.crt"
    )

    if version == "v3":
        cmd = (
            "{} ETCDCTL_API=3 /snap/bin/etcd.etcdctl --endpoints=http://localhost:4001 "
            'get "" --prefix --keys-only'.format(certs)
        )
        data = await juju_run(leader, cmd)
        return "etcd3key" in data.stdout.strip()
    else:
        return False


async def delete_data(leader):
    """
    Delete all dummy data on etcd
    """
    certs = (
        "ETCDCTL_KEY_FILE=/var/snap/etcd/common/client.key "
        "ETCDCTL_CERT_FILE=/var/snap/etcd/common/client.crt "
        "ETCDCTL_CA_FILE=/var/snap/etcd/common/ca.crt"
    )

    cmd = "{} ETCDCTL_API=2 /snap/bin/etcd.etcdctl rm /etcd2key".format(certs)
    await juju_run(leader, cmd)
    cmd = (
        "{} ETCDCTL_API=3 /snap/bin/etcdctl --endpoints=http://localhost:4001 "
        "del etcd3key".format(certs)
    )
    await juju_run(leader, cmd)
