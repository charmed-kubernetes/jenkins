import os
import pytest
from utils import temporary_model, conjureup, juju_deploy, deploy_e2e
from utils import upgrade_snaps, run_bundletester
from validation import validate_all

namespace = os.environ.get('TEST_SNAPS_NAMESPACE', 'containers')
channel = os.environ.get('TEST_SNAPS_CHANNEL', '1.7/edge')
bundles = [
    'kubernetes-core',
    #'canonical-kubernetes',
]


@pytest.mark.asyncio
@pytest.mark.parametrize('bundle', bundles)
async def test_deploy(bundle, log_dir):
    async with temporary_model(log_dir) as model:
        # await conjureup(model, namespace, bundle, channel)
        await juju_deploy(model, namespace, bundle, 'stable', channel)
        await deploy_e2e(model, 'stable', channel)
        await validate_all(model, log_dir)


@pytest.mark.asyncio
@pytest.mark.parametrize('bundle', bundles)
async def test_upgrade(bundle, log_dir):
    async with temporary_model(log_dir) as model:
        # await conjureup(model, namespace, bundle, 'stable')
        await juju_deploy(model, namespace, bundle, 'stable')
        await upgrade_snaps(model, channel)
        await deploy_e2e(model, 'stable', channel)
        await validate_all(model, log_dir)


@pytest.mark.asyncio
async def test_bundletester(log_dir):
    await run_bundletester(namespace, log_dir, snap_channel=channel)
