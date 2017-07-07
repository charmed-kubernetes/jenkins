import pytest
import rewrite_asserts
from utils import temporary_model, wait_for_ready, deploy_bundle
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
