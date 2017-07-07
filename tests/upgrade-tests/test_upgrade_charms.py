import pytest
import rewrite_asserts
from utils import temporary_model, wait_for_ready, conjureup
from validation import validate_all

test_cases = [
    # namespace, bundle, from channel, to channel, snap channel
    ('containers', 'kubernetes-core',      'stable', 'edge', '1.7/stable'),
    ('containers', 'canonical-kubernetes', 'stable', 'edge', '1.7/stable'),
]


@pytest.mark.asyncio
@pytest.mark.parametrize('namespace,bundle,from_channel,to_channel,snap_channel', test_cases)
async def test_upgrade_charms(namespace, bundle, from_channel, to_channel, snap_channel):
    async with temporary_model() as model:
        await conjureup(model, namespace, bundle, from_channel, snap_channel)
        await wait_for_ready(model)
        for app in model.applications.values():
            await app.upgrade_charm(channel=to_channel)
        await deploy_e2e(model, bundle, to_channel)
        await wait_for_ready(model)
        await validate_all(model)
