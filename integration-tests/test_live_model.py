# Tests an existing deployment.
# Assumes that a CDK deployment exists in the current Juju model.

import pytest
from juju.model import Model
from utils import captured_fail_logs, wait_for_ready
from validation import validate_all


@pytest.mark.asyncio
async def test_live_model(log_dir):
    model = Model()
    try:
        await model.connect_current()
        async with captured_fail_logs(model, log_dir):
            await wait_for_ready(model)
            await validate_all(model, log_dir)
    finally:
        await model.disconnect()
