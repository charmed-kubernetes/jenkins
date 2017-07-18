# Tests an existing deployment.
# Assumes that a CDK deployment exists in the current Juju model.

import pytest
from juju.model import Model
from utils import captured_fail_logs
from validation import validate_all

@pytest.mark.asyncio
async def test_live_model(log_dir):
    model = Model()
    try:
        await model.connect_current()
        async with captured_fail_logs(model, log_dir):
            await validate_all(model)
    finally:
        await model.disconnect()
