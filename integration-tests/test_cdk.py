import os
import pytest
from utils import temporary_model, deploy_e2e, upgrade_charms, upgrade_snaps
from utils import juju_deploy, run_bundletester
from validation import validate_all

namespace = os.environ.get('TEST_CHARM_NAMESPACE', 'containers')
charm_channel = os.environ.get('TEST_CHARM_CHANNEL', 'stable')
snap_channel = os.environ.get('TEST_SNAP_CHANNEL', '1.8/stable')
bundles_csv = os.environ.get('TEST_BUNDLES',
                             'canonical-kubernetes-canal,kubernetes-core')
bundles = [bundle.strip() for bundle in bundles_csv.split(',')]


@pytest.mark.asyncio
@pytest.mark.parametrize('bundle', bundles)
async def test_deploy(bundle, log_dir):
    async with temporary_model(log_dir) as model:
        # await conjureup(model, namespace, bundle, charm_channel,
        #                 snap_channel)
        await juju_deploy(model, namespace, bundle, charm_channel,
                          snap_channel)
        await deploy_e2e(model, charm_channel, snap_channel, namespace=namespace)
        await validate_all(model, log_dir)


@pytest.mark.asyncio
@pytest.mark.parametrize('bundle', bundles)
async def test_upgrade(bundle, log_dir):
    async with temporary_model(log_dir) as model:
        # await conjureup(model, namespace, bundle, 'stable')
        await juju_deploy(model, namespace, bundle, 'stable')
        await upgrade_charms(model, charm_channel)
        for app_name, blocking in {'kubernetes-master': True, 'kubernetes-worker': True, 'kubernetes-e2e': False}.items():
            # missing applications are simply not tested
            if model.applications.get(app_name):
                await upgrade_snaps(model, snap_channel, app_name, blocking)
        await deploy_e2e(model, charm_channel, snap_channel, namespace=namespace)
        await validate_all(model, log_dir)


@pytest.mark.asyncio
async def test_bundletester(log_dir):
    await run_bundletester(namespace, log_dir, channel=charm_channel,
                           snap_channel=snap_channel)
