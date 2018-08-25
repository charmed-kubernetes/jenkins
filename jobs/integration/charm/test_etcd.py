import asyncio
import pytest
import os
from sh import juju_wait
from .. import base

# Locally built charm layer path
ETCD_CHARM_PATH = os.getenv('CHARM_PATH')
J_CONTROLLER = os.getenv('CONTROLLER')
J_MODEL = os.getenv('MODEL')

_juju_wait = juju_wait.bake('-e', "{}:{}".format(J_CONTROLLER, J_MODEL), '-w')

pytestmark = pytest.mark.asyncio


@pytest.yield_fixture(scope='module')
def event_loop():
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope='module')
async def deploy():
    test_model = base.TestModel()
    deployment = await test_model.connect()
    await deployment.deploy(str(ETCD_CHARM_PATH))
    await deployment.deploy('cs:~containers/easyrsa')
    await deployment.add_relation('easyrsa:client',
                                  'etcd:certificates')
    _juju_wait()
    yield deployment
    await test_model.disconnect()


async def test_local_deployed(deploy, event_loop):
    """ Verify local etcd charm can be deployed """
    assert 'etcd' in deploy.applications


async def test_leader_status(deploy, event_loop):
    """ Verify our leader is running the etcd daemon """
    for unit in deploy.applications['etcd'].units:
        is_leader = await unit.is_leader_from_status()
        if is_leader:
            status = await unit.run('systemctl is-active snap.etcd.etcd')
            assert "inactive" not in status.results['Stdout']
            assert "active" in status.results['Stdout']


async def test_config_snapd_refresh(deploy, event_loop):
    """ Verify initial snap refresh config is set and can be changed """
    etcd = deploy.applications['etcd']
    for unit in etcd.units:
        is_leader = await unit.is_leader_from_status()
        if is_leader:
            # default timer should be some day of the week followed by a number
            timer = await unit.run('snap get core refresh.timer')
            assert len(timer.results['Stdout'].strip()) == len('dayX')

            # verify a new timer value
            await etcd.set_config({'snapd_refresh': 'fri5'})
            timer = await unit.run('snap get core refresh.timer')
            assert timer.results['Stdout'].strip() == 'fri5'


async def test_node_scale(deploy, event_loop):
    """ Scale beyond 1 node because etcd supports peering as a standalone
    application. """
    # Ensure we aren't testing a single node
    etcd = deploy.applications['etcd']
    if not len(etcd.units) > 1:
        await etcd.add_units(count=2)
        _juju_wait()

    for unit in etcd.units:
        out = await unit.run('systemctl is-active snap.etcd.etcd')
        assert out.status == 'completed'
        assert "inactive" not in out.results['Stdout']
        assert "active" in out.results['Stdout']


async def test_cluster_health(deploy, event_loop):
    """ Iterate all the units and verify we have a clean bill of health
    from etcd """

    certs = "ETCDCTL_KEY_FILE=/var/snap/etcd/common/client.key " \
            "ETCDCTL_CERT_FILE=/var/snap/etcd/common/client.crt " \
            "ETCDCTL_CA_FILE=/var/snap/etcd/common/ca.crt"

    etcd = deploy.applications['etcd']
    for unit in etcd.units:
        cmd = '{} /snap/bin/etcdctl cluster-health'.format(certs)
        health = await unit.run(cmd)
        assert 'unhealthy' not in health.results['Stdout']
        assert 'unavailable' not in health.results['Stdout']


async def test_leader_knows_all_members(deploy, event_loop):
    """ Test we have the same number of units deployed and reporting in
    the etcd cluster as participating """

    # The spacing here is semi-important as its a string of ENV exports
    # also, this is hard coding for the defaults. if the defaults in
    # layer.yaml change, this will need to change.
    certs = "ETCDCTL_KEY_FILE=/var/snap/etcd/common/client.key " \
            "ETCDCTL_CERT_FILE=/var/snap/etcd/common/client.crt " \
            "ETCDCTL_CA_FILE=/var/snap/etcd/common/ca.crt"

    # format the command, and execute on the leader
    cmd = '{} /snap/bin/etcd.etcdctl member list'.format(certs)
    etcd = deploy.applications['etcd']
    for unit in etcd.units:
        is_leader = await unit.is_leader_from_status()
        if is_leader:
            out = await unit.run(cmd)
            # turn the output into a list so we can iterate
            members = out.results['Stdout'].strip()
            members = members.split('\n')
            for item in members:
                # this is responded when TLS is enabled and we don't have
                # proper Keys. This is kind of a "ssl works test" but of
                # the worse variety... assuming the full stack completed.
                assert 'etcd cluster is unavailable' not in members
            assert len(members) == len(etcd.units)


async def test_node_scale_down_members(deploy, event_loop):
    """ Scale the cluster down and ensure the cluster state is still
    healthy """

    # Remove the leader
    etcd = deploy.applications['etcd']
    for unit in etcd.units:
        is_leader = await unit.is_leader_from_status()
        if is_leader:
            unit_name_copy = unit.name
            await etcd.destroy_unit(unit.name)
            # cory_fu> stokachu: It would be really good to add that to
            # libjuju, but in the meantime you could use either
            # `block_until(lambda: unit.name not in [u.name for u in
            # etcd.units])` or `e = asyncio.Event(); unit.on_remove(e.set);
            # await e.wait()`
            await deploy.block_until(
                lambda: unit_name_copy not in [u.name for u in etcd.units])
    _juju_wait()
    # re-use the cluster-health test to validate we are still healthy.
    await test_cluster_health(deploy, event_loop)
