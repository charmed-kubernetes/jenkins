import pytest
from utils import temporary_model, wait_for_ready, assert_healthy

SNAPS_UPGRADE_FROM='1.6/stable'
SNAPS_UPGRADE_TO='1.6/edge'

@pytest.mark.asyncio
async def test_upgrade_snaps():
    async with temporary_model() as model:
        await model.deploy('kubernetes-core', channel='stable')
        await model.applications['kubernetes-master'].set_config({'channel': SNAPS_UPGRADE_FROM})
        await model.applications['kubernetes-worker'].set_config({'channel': SNAPS_UPGRADE_FROM})
        await wait_for_ready(model)
        await model.applications['kubernetes-master'].set_config({'channel': SNAPS_UPGRADE_TO})
        await model.applications['kubernetes-worker'].set_config({'channel': SNAPS_UPGRADE_TO})
        for unit in model.applications['kubernetes-worker'].units:
            action = await unit.run_action('upgrade')
            await action.wait()
            assert action.status == 'completed'
        await wait_for_ready(model)
        assert_healthy(model)
