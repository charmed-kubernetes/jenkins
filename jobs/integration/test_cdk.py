import os
import pytest
from .utils import upgrade_charms, upgrade_snaps
from .validation import validate_all
from .base import UseModel

namespace = os.environ.get('TEST_CHARM_NAMESPACE', 'containers')
test_charm_channel = os.environ.get('TEST_CHARM_CHANNEL', 'edge')
test_snap_channel = os.environ.get('TEST_SNAP_CHANNEL', 'edge')
test_cloud = os.environ.get('TEST_CLOUD', '')
upgrade_from_snap_channel = os.environ.get(
    'UPGRADE_FROM_SNAP_CHANNEL', 'stable')
upgrade_from_charm_channel = os.environ.get(
    'UPGRADE_FROM_CHARM_CHANNEL', 'stable')


@pytest.mark.asyncio
async def test_validate(log_dir):
    """ Validates and existing CDK deployment
    """
    async with UseModel() as model:
        await validate_all(model, log_dir)


@pytest.mark.asyncio
async def test_upgrade(log_dir):
    async with UseModel() as model:
        await upgrade_charms(model, test_charm_channel)
        await upgrade_snaps(model, test_snap_channel)
        await validate_all(model, log_dir)
