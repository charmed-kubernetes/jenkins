import pytest
from utils import temporary_model, conjureup, deploy_e2e, upgrade_charms
from validation import validate_all

test_cases = [
    # namespace    # bundle                # channel  # snap channel
    ('containers', 'kubernetes-core',      'edge',    '1.7/stable'),
    #('containers', 'canonical-kubernetes', 'edge',    '1.7/stable'),
]


@pytest.mark.asyncio
@pytest.mark.parametrize('namespace,bundle,channel,snap_channel', test_cases)
async def test_deploy(namespace, bundle, channel, snap_channel, log_dir):
    async with temporary_model(log_dir) as model:
        await conjureup(model, namespace, bundle, channel, snap_channel)
        await deploy_e2e(model, channel, snap_channel)
        await validate_all(model)


@pytest.mark.asyncio
@pytest.mark.parametrize('namespace,bundle,channel,snap_channel', test_cases)
async def test_upgrade(namespace, bundle, channel, snap_channel, log_dir):
    async with temporary_model(log_dir) as model:
        await conjureup(model, namespace, bundle, 'stable', snap_channel)
        await upgrade_charms(model, channel)
        await deploy_e2e(model, channel, snap_channel)
        await validate_all(model)


@pytest.mark.parametrize('namespace,bundle,channel,snap_channel', test_cases)
def test_bundletester(namespace, bundle, channel, snap_channel, log_dir):
    assert False, "TODO"
