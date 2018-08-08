import asyncio
import os
import pytest
from utils import upgrade_charms, upgrade_snaps
from utils import run_bundletester
from validation import validate_all
from juju.model import Model

namespace = os.environ.get('TEST_CHARM_NAMESPACE', 'containers')
test_charm_channel = os.environ.get('TEST_CHARM_CHANNEL', 'edge')
test_snap_channel = os.environ.get('TEST_SNAP_CHANNEL', 'edge')
test_cloud = os.environ.get('TEST_CLOUD', '')
upgrade_from_snap_channel = os.environ.get(
    'UPGRADE_FROM_SNAP_CHANNEL', 'stable')
upgrade_from_charm_channel = os.environ.get(
    'UPGRADE_FROM_CHARM_CHANNEL', 'stable')
juju_controller = os.environ.get('CONTROLLER', 'jenkins-ci-aws')
juju_model = os.environ.get(
    'MODEL', 'validate-{}'.format(os.environ['BUILD_NUMBER']))


@pytest.mark.asyncio
async def test_validate(log_dir):
    """ Validates and existing CDK deployment
    """
    model = Model(asyncio.get_event_loop())
    model_name = "{}:{}".format(juju_controller,
                                juju_model)
    await model.connect(model_name)
    await validate_all(model, log_dir)
    await model.disconnect()


@pytest.mark.asyncio
async def test_upgrade(log_dir):
    model = Model(asyncio.get_event_loop())
    model_name = "{}:{}".format(juju_controller,
                                juju_model)
    await model.connect(model_name)
    await upgrade_charms(model, test_charm_channel)
    await upgrade_snaps(model, test_snap_channel)
    await validate_all(model, log_dir)
    await model.disconnect()


@pytest.mark.asyncio
async def test_bundletester(log_dir):
    await run_bundletester(namespace, log_dir, channel=test_charm_channel,
                           snap_channel=test_snap_channel,
                           force_cloud=test_cloud)
