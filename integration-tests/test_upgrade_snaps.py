import pytest
from utils import temporary_model, conjureup, deploy_e2e
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
async def test_upgrade_snaps(namespace, bundle, charm_channel, from_channel, to_channel, log_dir):
    async with temporary_model(log_dir) as model:
        await conjureup(model, namespace, bundle, charm_channel, from_channel)
        await set_snap_channel(model, to_channel)
        for unit in model.applications['kubernetes-worker'].units:
            action = await unit.run_action('upgrade')
            await action.wait()
            assert action.status == 'completed'
        await deploy_e2e(model, charm_channel, to_channel)
        await validate_all(model)
