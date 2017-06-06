import pytest
from utils import temporary_model, wait_for_ready, assert_healthy

CHARMS_UPGRADE_FROM="stable"
CHARMS_UPGRADE_TO="beta"

@pytest.mark.asyncio
async def test_upgrade_charms():
    async with temporary_model() as model:
        await model.deploy("kubernetes-core", channel=CHARMS_UPGRADE_FROM)
        await wait_for_ready(model)
        await model.applications["easyrsa"].upgrade_charm(channel=CHARMS_UPGRADE_TO)
        await model.applications["etcd"].upgrade_charm(channel=CHARMS_UPGRADE_TO)
        await model.applications["flannel"].upgrade_charm(channel=CHARMS_UPGRADE_TO)
        await model.applications["kubernetes-master"].upgrade_charm(channel=CHARMS_UPGRADE_TO)
        await model.applications["kubernetes-worker"].upgrade_charm(channel=CHARMS_UPGRADE_TO)
        await wait_for_ready(model)
        assert_healthy(model)
