import pytest
import rewrite_asserts
from utils import temporary_model, wait_for_ready, deploy_bundle, add_new_e2e_relation
from validation import validate_all

test_cases = [
    # bundle                 from_channel  to_channel
    ('kubernetes-core',      'stable',     'edge'),
    ('canonical-kubernetes', 'stable',     'edge'),
]


@pytest.mark.asyncio
@pytest.mark.parametrize('bundle,from_channel,to_channel', test_cases)
async def test_upgrade_charms(bundle, from_channel, to_channel):
    async with temporary_model() as model:
        await deploy_bundle(model, bundle, from_channel)
        await wait_for_ready(model)
        for app in model.applications.values():
            await app.upgrade_charm(channel=to_channel)
        await add_new_e2e_relation(model)
        await wait_for_ready(model)
        await validate_all(model)
