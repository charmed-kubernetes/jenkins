import os
import pytest
from utils import temporary_model, deploy_e2e, upgrade_charms, upgrade_snaps
from utils import juju_deploy, run_bundletester, default_bundles
from validation import validate_all

namespace = os.environ.get('TEST_CHARM_NAMESPACE', 'containers')
test_charm_channel = os.environ.get('TEST_CHARM_CHANNEL', 'edge')
test_snap_channel = os.environ.get('TEST_SNAP_CHANNEL', 'edge')
test_cloud = os.environ.get('TEST_CLOUD', '')
bundles_csv = os.environ.get('TEST_BUNDLES', default_bundles())
upgrade_from_snap_channel = os.environ.get('UPGRADE_FROM_SNAP_CHANNEL', 'stable')
upgrade_from_charm_channel = os.environ.get('UPGRADE_FROM_CHARM_CHANNEL', 'stable')
bundles = [bundle.strip() for bundle in bundles_csv.split(',')]


@pytest.mark.asyncio
@pytest.mark.parametrize('bundle', bundles)
async def test_deploy(bundle, log_dir):
    async with temporary_model(log_dir, force_cloud=test_cloud) as model:
        # await conjureup(model, namespace, bundle, test_charm_channel,
        #                 snap_channel)
        await juju_deploy(model, namespace, bundle, test_charm_channel,
                          test_snap_channel)
        await deploy_e2e(model, test_charm_channel, test_snap_channel,
                         namespace=namespace)
        await validate_all(model, log_dir)


@pytest.mark.asyncio
@pytest.mark.parametrize('bundle', bundles)
async def test_upgrade(bundle, log_dir):
    async with temporary_model(log_dir, force_cloud=test_cloud) as model:
        # await conjureup(model, namespace, bundle, 'stable')
        await juju_deploy(model, namespace, bundle, upgrade_from_charm_channel,
                          upgrade_from_snap_channel)
        await upgrade_charms(model, test_charm_channel)
        await upgrade_snaps(model, test_snap_channel)
        await deploy_e2e(model, test_charm_channel,
                         test_snap_channel, namespace=namespace)
        await validate_all(model, log_dir)


@pytest.mark.asyncio
async def test_bundletester(log_dir):
    await run_bundletester(namespace, log_dir, channel=test_charm_channel,
                           snap_channel=test_snap_channel,
                           force_cloud=test_cloud)
