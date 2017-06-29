import pytest
import rewrite_asserts
from utils import temporary_model, wait_for_ready, get_model, deploy_bundle
from validation import validate_all

test_cases = [
    # bundle                 # channel
    ('kubernetes-core',      'edge'),
    ('canonical-kubernetes', 'edge'),
]

@pytest.mark.asyncio
@pytest.mark.parametrize('bundle,channel', test_cases)
async def test_deploy(bundle, channel):
    async with temporary_model() as model:
        await deploy_bundle(model, bundle, channel)
        await wait_for_ready(model)
        await validate_all(model)


'''
@pytest.mark.asyncio
@pytest.mark.parametrize('bundle,channel', test_cases)
async def test_deploy(bundle, channel):
    model = await get_model('t1')
    #await model.deploy(bundle, channel=channel)
    #await model.deploy('cs:~containers/kubernetes-e2e', channel=channel)
    #await model.add_relation('kubernetes-e2e', 'kubernetes-master')
    #await model.add_relation('kubernetes-e2e', 'easyrsa')
    await wait_for_ready(model)
    await validate_all(model)
'''
