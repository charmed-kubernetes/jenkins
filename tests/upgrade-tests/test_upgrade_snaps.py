import pytest
import rewrite_asserts
from utils import temporary_model, wait_for_ready, conjureup
from validation import validate_all

test_cases = [
    # namespace, bundle, charm channel, snap from channel, snap to channel
    ('containers', 'kubernetes-core',      'edge', '1.6/stable', '1.7/stable'),
    ('containers', 'canonical-kubernetes', 'edge', '1.6/stable', '1.7/stable'),
]


async def set_snap_channel(model, channel):
    master = model.applications['kubernetes-master']
    await master.set_config({'channel': channel})
    worker = model.applications['kubernetes-worker']
    await worker.set_config({'channel': channel})


@pytest.mark.asyncio
@pytest.mark.parametrize('namespace,bundle,charm_channel,from_channel,to_channel',
                         test_cases)
async def test_upgrade_snaps(namespace, bundle, charm_channel, from_channel, to_channel):
    async with temporary_model() as model:
        await conjureup(model, namespace, bundle, charm_channel, from_channel)
        await set_snap_channel(model, from_channel)
        await wait_for_ready(model)
        await set_snap_channel(model, to_channel)
        for unit in model.applications['kubernetes-worker'].units:
            action = await unit.run_action('upgrade')
            await action.wait()
            assert action.status == 'completed'
        await wait_for_ready(model)
        await validate_all(model)
