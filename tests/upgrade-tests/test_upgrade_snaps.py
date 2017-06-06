import pytest
from utils import temporary_model, wait_for_ready, assert_healthy

test_cases = [
    # bundle                 from_channel  to_channel
    ('kubernetes-core',      '1.6/stable', '1.6/edge'),
    ('kubernetes-core',      '1.6/stable', '1.7/edge'),
    ('canonical-kubernetes', '1.6/stable', '1.6/edge'),
    ('canonical-kubernetes', '1.6/stable', '1.7/edge'),
]


async def set_snap_channel(model, channel):
    master = model.applications['kubernetes-master']
    await master.set_config({'channel': channel})
    worker = model.applications['kubernetes-worker']
    await worker.set_config({'channel': channel})


@pytest.mark.asyncio
@pytest.mark.parametrize('bundle,from_channel,to_channel', test_cases)
async def test_upgrade_snaps(bundle, from_channel, to_channel):
    async with temporary_model() as model:
        await model.deploy(bundle, channel='stable')
        await set_snap_channel(model, from_channel)
        await wait_for_ready(model)
        await set_snap_channel(model, to_channel)
        for unit in model.applications['kubernetes-worker'].units:
            action = await unit.run_action('upgrade')
            await action.wait()
            assert action.status == 'completed'
        await wait_for_ready(model)
        assert_healthy(model)
