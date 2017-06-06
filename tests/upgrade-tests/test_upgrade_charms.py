import pytest
from utils import temporary_model, wait_for_ready, assert_healthy

test_cases = [
    # bundle                 from_channel  to_channel
    ('kubernetes-core',      'stable',     'beta'),
    ('canonical-kubernetes', 'stable',     'beta'),
]


@pytest.mark.asyncio
@pytest.mark.parametrize('bundle,from_channel,to_channel', test_cases)
async def test_upgrade_charms(bundle, from_channel, to_channel):
    async with temporary_model() as model:
        await model.deploy(bundle, channel=from_channel)
        await wait_for_ready(model)
        for app in model.applications.values():
            await app.upgrade_charm(channel=to_channel)
        await wait_for_ready(model)
        assert_healthy(model)
