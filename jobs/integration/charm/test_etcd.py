import pytest
import os
from sh import juju_wait
from .. import base
from subprocess import check_call

# Locally built charm layer path
ETCD_CHARM_PATH = os.getenv('CHARM_PATH')

pytestmark = pytest.mark.asyncio


def _juju_wait(model):
    _controller = os.environ.get('CONTROLLER', 'jenkins-ci-aws')
    juju_wait('-e', "{}:{}".format(_controller, model), '-w')


async def test_local_deployed(event_loop):
    """ Verify local etcd charm can be deployed """
    async with base.CleanModel() as model:
        await model.deploy(str(ETCD_CHARM_PATH))
        await model.deploy('cs:~containers/easyrsa')
        await model.add_relation('easyrsa:client',
                                 'etcd:certificates')
        _juju_wait(model.info.name)

        assert 'etcd' in model.applications


async def test_leader_status(event_loop):
    """ Verify our leader is running the etcd daemon """
    async with base.CleanModel() as model:
        etcd = await model.deploy(str(ETCD_CHARM_PATH))
        await model.deploy('cs:~containers/easyrsa')
        await model.add_relation('easyrsa:client',
                                 'etcd:certificates')
        await etcd.set_config({'channel': '3.0/stable'})
        _juju_wait(model.info.name)
        for unit in etcd.units:
            is_leader = await unit.is_leader_from_status()
            if is_leader:
                status = await unit.run('systemctl is-active snap.etcd.etcd')
                assert "inactive" not in status.results['Stdout'].strip()
                assert "active" in status.results['Stdout'].strip()


async def test_config_snapd_refresh(event_loop):
    """ Verify initial snap refresh config is set and can be changed """
    async with base.CleanModel() as model:
        etcd = await model.deploy(str(ETCD_CHARM_PATH))
        await model.deploy('cs:~containers/easyrsa')
        await model.add_relation('easyrsa:client',
                                 'etcd:certificates')
        await etcd.set_config({'channel': '3.0/stable'})
        _juju_wait(model.info.name)
        for unit in etcd.units:
            is_leader = await unit.is_leader_from_status()
            if is_leader:
                # default timer should be some day of the week followed by a
                # number
                timer = await unit.run('snap get core refresh.timer')
                assert len(timer.results['Stdout'].strip()) == len('dayX')

                # verify a new timer value
                await etcd.set_config({'snapd_refresh': 'fri5'})
                timer = await unit.run('snap get core refresh.timer')
                assert timer.results['Stdout'].strip() == 'fri5'


async def test_node_scale(event_loop):
    """ Scale beyond 1 node because etcd supports peering as a standalone
    application. """
    async with base.CleanModel() as model:
        etcd = await model.deploy(str(ETCD_CHARM_PATH))
        await model.deploy('cs:~containers/easyrsa')
        await model.add_relation('easyrsa:client',
                                 'etcd:certificates')
        # Ensure we aren't testing a single node
        await etcd.set_config({'channel': '3.0/stable'})
        _juju_wait(model.info.name)
        if not len(etcd.units) > 1:
            await etcd.add_units(count=2)
            _juju_wait(model.info.name)

        for unit in etcd.units:
            out = await unit.run('systemctl is-active snap.etcd.etcd')
            assert out.status == 'completed'
            assert "inactive" not in out.results['Stdout'].strip()
            assert "active" in out.results['Stdout'].strip()


async def test_cluster_health(event_loop):
    """ Iterate all the units and verify we have a clean bill of health
    from etcd """
    certs = "ETCDCTL_KEY_FILE=/var/snap/etcd/common/client.key " \
            "ETCDCTL_CERT_FILE=/var/snap/etcd/common/client.crt " \
            "ETCDCTL_CA_FILE=/var/snap/etcd/common/ca.crt"

    async with base.CleanModel() as model:
        etcd = await model.deploy(str(ETCD_CHARM_PATH))
        await model.deploy('cs:~containers/easyrsa')
        await model.add_relation('easyrsa:client',
                                 'etcd:certificates')
        await etcd.set_config({'channel': '3.0/stable'})
        _juju_wait(model.info.name)
        for unit in etcd.units:
            cmd = '{} /snap/bin/etcdctl cluster-health'.format(certs)
            health = await unit.run(cmd)
            assert 'unhealthy' not in health.results['Stdout'].strip()
            assert 'unavailable' not in health.results['Stdout'].strip()


async def test_leader_knows_all_members(event_loop):
    """ Test we have the same number of units deployed and reporting in
    the etcd cluster as participating """

    # The spacing here is semi-important as its a string of ENV exports
    # also, this is hard coding for the defaults. if the defaults in
    # layer.yaml change, this will need to change.
    certs = "ETCDCTL_KEY_FILE=/var/snap/etcd/common/client.key " \
            "ETCDCTL_CERT_FILE=/var/snap/etcd/common/client.crt " \
            "ETCDCTL_CA_FILE=/var/snap/etcd/common/ca.crt"

    async with base.CleanModel() as model:
        etcd = await model.deploy(str(ETCD_CHARM_PATH))
        await model.deploy('cs:~containers/easyrsa')
        await model.add_relation('easyrsa:client',
                                 'etcd:certificates')
        await etcd.set_config({'channel': '3.0/stable'})
        _juju_wait(model.info.name)

        # format the command, and execute on the leader
        cmd = '{} /snap/bin/etcd.etcdctl member list'.format(certs)

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


async def test_node_scale_down_members(event_loop):
    """ Scale the cluster down and ensure the cluster state is still
    healthy """
    async with base.CleanModel() as model:
        etcd = await model.deploy(str(ETCD_CHARM_PATH))
        await model.deploy('cs:~containers/easyrsa')
        await model.add_relation('easyrsa:client',
                                 'etcd:certificates')
        await etcd.set_config({'channel': '3.0/stable'})
        _juju_wait(model.info.name)

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
                await model.block_until(
                    lambda: unit_name_copy not in [u.name for u in etcd.units])
        _juju_wait(model.info.name)
        # re-use the cluster-health test to validate we are still healthy.
        await test_cluster_health(event_loop)


async def test_set_fixture_data(event_loop):
    """ Preseed data """
    async with base.CleanModel() as model:
        etcd = await model.deploy(str(ETCD_CHARM_PATH))
        await model.deploy('cs:~containers/easyrsa')
        await model.add_relation('easyrsa:client',
                                 'etcd:certificates')
        await etcd.set_config({'channel': '3.0/stable'})
        _juju_wait(model.info.name)

        for unit in etcd.units:
            is_leader = await unit.is_leader_from_status()
            if is_leader:
                certs = "ETCDCTL_KEY_FILE=/etc/ssl/etcd/client.key " \
                    "ETCDCTL_CERT_FILE=/etc/ssl/etcd/client.crt " \
                    "ETCDCTL_CA_FILE=/etc/ssl/etcd/ca.crt"

                await unit.run(
                    '{} /snap/bin/etcd.etcdctl set juju rocks'.format(certs))
                await unit.run(
                    '{} /snap/bin/etcd.etcdctl set nested/data works'.format(
                        certs))


async def test_snap_action(event_loop):
    ''' When the charm is upgraded, a message should appear requesting the
    user to run a manual upgrade.'''
    async with base.CleanModel() as model:
        etcd = await model.deploy(str(ETCD_CHARM_PATH))
        await model.deploy('cs:~containers/easyrsa')
        await model.add_relation('easyrsa:client',
                                 'etcd:certificates')
        _juju_wait(model.info.name)

        for unit in etcd.units:
            is_leader = await unit.is_leader_from_status()
            if is_leader:
                action = await unit.run_action('snap-upgrade')
                action = await action.wait()

                # This will fail if the upgrade didnt work
                assert 'completed' in action.results.status
                await validate_running_snap_daemon(etcd)
                await validate_etcd_fixture_data(etcd)


async def test_snap_upgrade_to_three_oh(event_loop):
    ''' Default configured channel is 2.3/stable. Ensure we can jump to
    3.0 '''
    async with base.CleanModel() as model:
        etcd = await model.deploy(str(ETCD_CHARM_PATH))
        await model.deploy('cs:~containers/easyrsa')
        await model.add_relation('easyrsa:client',
                                 'etcd:certificates')

        await etcd.set_config({'channel': '3.0/stable'})

        _juju_wait(model.info.name)
        await validate_running_snap_daemon(etcd)
        await validate_etcd_fixture_data(etcd)


async def validate_etcd_fixture_data(etcd):
    ''' Recall data set by set_etcd_fixture_data to ensure it persisted
    through the upgrade '''

    # The spacing here is semi-important as its a string of ENV exports
    # also, this is hard coding for the defaults. if the defaults in
    # layer.yaml change, this will need to change.
    certs = "ETCDCTL_KEY_FILE=/var/snap/etcd/common/client.key " \
            "ETCDCTL_CERT_FILE=/var/snap/etcd/common/client.crt " \
            "ETCDCTL_CA_FILE=/var/snap/etcd/common/ca.crt"

    for unit in etcd.units:
        is_leader = await unit.is_leader_from_status()
        if is_leader:
            jcmd = "{} /snap/bin/etcd.etcdctl get juju".format(certs)
            juju_key = await unit.run(jcmd)
            nscmd = "{} /snap/bin/etcd.etcdctl get nested/data".format(certs)
            nested_key = await unit.run(nscmd)

            assert 'rocks' in juju_key.result['Stdout'].strip()
            assert 'works' in nested_key.results['Stdout'].strip()


async def validate_running_snap_daemon(etcd):
    ''' Validate the snap based etcd daemon is running after an op '''
    for unit in etcd.units:
        is_leader = await unit.is_leader_from_status()
        if is_leader:
            daemon_status = await unit.run(
                'systemctl is-active snap.etcd.etcd')
            assert 'active' in daemon_status.results['Stdout'].strip()


async def load_data(leader):
    """
    Load dummy data

    """
    certs = "ETCDCTL_KEY_FILE=/var/snap/etcd/common/client.key " \
            "ETCDCTL_CERT_FILE=/var/snap/etcd/common/client.crt " \
            "ETCDCTL_CA_FILE=/var/snap/etcd/common/ca.crt"

    cmd = '{} ETCDCTL_API=2 /snap/bin/etcd.etcdctl set /etcd2key etcd2value'.format(
        certs)
    await leader.run(cmd)
    cmd = '{} ETCDCTL_API=3 /snap/bin/etcd.etcdctl --endpoints=http://localhost:4001 ' \
          'put etcd3key etcd3value'.format(certs)
    await leader.run(cmd)


async def is_data_present(leader, version):
    '''
    Check if we have the data present on the datastore of the version
    Args:
        version: v2 or v3 etcd datastore

    Returns: True if the data is present

    '''
    certs = "ETCDCTL_KEY_FILE=/var/snap/etcd/common/client.key " \
            "ETCDCTL_CERT_FILE=/var/snap/etcd/common/client.crt " \
            "ETCDCTL_CA_FILE=/var/snap/etcd/common/ca.crt"

    if version == 'v2':
        cmd = '{} ETCDCTL_API=2 /snap/bin/etcd.etcdctl ls'.format(certs)
        data = await leader.run(cmd)
        return 'etcd2key' in data.results['Stdout'].strip()
    elif version == 'v3':
        cmd = '{} ETCDCTL_API=3 /snap/bin/etcd.etcdctl --endpoints=http://localhost:4001 ' \
              'get "" --prefix --keys-only'.format(certs)
        data = await leader.run(cmd)
        return 'etcd3key' in data.results['Stdout'].strip()
    else:
        return False


async def delete_data(leader):
    '''
    Delete all dummy data on etcd
    '''
    certs = "ETCDCTL_KEY_FILE=/var/snap/etcd/common/client.key " \
            "ETCDCTL_CERT_FILE=/var/snap/etcd/common/client.crt " \
            "ETCDCTL_CA_FILE=/var/snap/etcd/common/ca.crt"

    cmd = '{} ETCDCTL_API=2 /snap/bin/etcd.etcdctl rm /etcd2key'.format(certs)
    await leader.run(cmd)
    cmd = '{} ETCDCTL_API=3 /snap/bin/etcdctl --endpoints=http://localhost:4001 ' \
          'del etcd3key'.format(certs)
    await leader.run(cmd)


@pytest.mark.skip("Needs work")
async def test_snapshot_restore(etcd):
    """
    Trigger snapshot and restore actions
    """
    async with base.CleanModel() as model:
        etcd = await model.deploy(str(ETCD_CHARM_PATH))
        await model.deploy('cs:~containers/easyrsa')
        await model.add_relation('easyrsa:client',
                                 'etcd:certificates')

        await etcd.set_config({'channel': '3.0/stable'})

        _juju_wait(model.info.name)

        for unit in etcd.units:
            leader = await unit.is_leader_from_status()
            if leader:
                # Load dummy data
                await load_data(leader)
                for ver in ['v2', 'v3']:
                    assert await is_data_present(leader, ver)
                filenames = {}
                for dataset in ['v2', 'v3']:
                    # Take snapshot of data
                    action = await leader.run_action('snapshot', {'keys-version': dataset})
                    action = await action.wait()
                    assert action.status == 'completed'
                    print(action.results) # ['copy']['cmd']
                    # cpcmd = action.results['Stdout'].strip()
                    # subprocess.check_call(cpcmd.split())
                    # filenames[dataset] = os.path.basename(outcome['results']['snapshot']['path'])

                delete_data(leader)
                for ver in ['v2', 'v3']:
                    assert await is_data_present(leader, ver) is False

                # Restore v2 data
                cmd = 'juju attach etcd snapshot=%s' % filenames['v2']
                check_call(cmd.split())
                action = await leader.run_action('restore')
                action = await action.wait()
                assert action.status == 'completed'
                for ver in ['v2', 'v3']:
                    assert await is_data_present(leader, ver) is True

                # Restore v3 data
                cmd = 'juju attach etcd snapshot=%s' % filenames['v3']
                check_call(cmd.split())
                action = await leader.run_action('restore')
                action = await action.wait()
                await action.status == 'completed'
                for ver in ['v2', 'v3']:
                    assert await is_data_present(leader, ver) is True
