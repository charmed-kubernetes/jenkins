import os
import pytest
from utils import temporary_model, deploy_e2e, upgrade_charms, upgrade_snaps
from utils import juju_deploy, run_bundletester, default_bundles
from validation import validate_all

namespace = os.environ.get('TEST_CHARM_NAMESPACE', 'containers')
charm_channel = os.environ.get('TEST_CHARM_CHANNEL', 'stable')
snap_channel = os.environ.get('TEST_SNAP_CHANNEL', '1.8/stable')
test_cloud = os.environ.get('TEST_CLOUD', '')
bundles_csv = os.environ.get('TEST_BUNDLES', default_bundles())
bundles = [bundle.strip() for bundle in bundles_csv.split(',')]


@pytest.mark.asyncio
@pytest.mark.parametrize('bundle', bundles)
async def test_deploy(bundle, log_dir):
    async with temporary_model(log_dir, test_cloud) as model:
        # await conjureup(model, namespace, bundle, charm_channel,
        #                 snap_channel)
        await juju_deploy(model, namespace, bundle, charm_channel,
                          snap_channel)
        await deploy_e2e(model, charm_channel, snap_channel, namespace=namespace)
        await validate_all(model, log_dir)


@pytest.mark.asyncio
@pytest.mark.parametrize('bundle', bundles)
async def test_upgrade(bundle, log_dir):
    async with temporary_model(log_dir, test_cloud) as model:
        # await conjureup(model, namespace, bundle, 'stable')
        await juju_deploy(model, namespace, bundle, 'stable')
        await upgrade_charms(model, charm_channel)
        await upgrade_snaps(model, snap_channel)
        await deploy_e2e(model, charm_channel, snap_channel, namespace=namespace)
        await validate_all(model, log_dir)


@pytest.mark.asyncio
async def test_bundletester(log_dir):
    await run_bundletester(namespace, log_dir, channel=charm_channel,
                           snap_channel=snap_channel, force_cloud=test_cloud)
