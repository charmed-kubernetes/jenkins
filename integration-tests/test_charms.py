import os
import pytest
from utils import temporary_model, conjureup, deploy_e2e, upgrade_charms
from utils import juju_deploy, run_bundletester
from validation import validate_all

namespace = os.environ.get('TEST_CHARMS_NAMESPACE', 'containers')
channel = os.environ.get('TEST_CHARMS_CHANNEL', 'edge')
bundles = [
    'kubernetes-core',
    #'canonical-kubernetes',
]


@pytest.mark.asyncio
@pytest.mark.parametrize('bundle', bundles)
async def test_deploy(bundle, log_dir):
    async with temporary_model(log_dir) as model:
        # await conjureup(model, namespace, bundle, channel)
        await juju_deploy(model, namespace, bundle, channel)
        await deploy_e2e(model, channel)
        await validate_all(model, log_dir)


@pytest.mark.asyncio
@pytest.mark.parametrize('bundle', bundles)
async def test_upgrade(bundle, log_dir):
    async with temporary_model(log_dir) as model:
        # await conjureup(model, namespace, bundle, 'stable')
        await juju_deploy(model, namespace, bundle, channel)
        await upgrade_charms(model, channel)
        await deploy_e2e(model, channel)
        await validate_all(model, log_dir)


@pytest.mark.asyncio
async def test_bundletester(log_dir):
    await run_bundletester(namespace, log_dir, channel=channel)
