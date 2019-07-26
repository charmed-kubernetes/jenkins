"""
Test Containerd charm specific.
"""
import pytest

from ..logger import log
from ..utils import (
    _juju_wait,
    asyncify,
    retry_async_with_timeout
)


@pytest.mark.asyncio
async def test_containerd_no_gpu(model):
    """
    Mostly a place holder.
    """
    worker_app = model.applications['containerd']

    async def verify_ps_output(worker, opt):
        action = await worker.run('ps -aux | grep containerd')
        return opt in action.results['Stdout']

    log('validating containerd no gpu')

    await worker_app.set_config({'gpu_driver': 'none'})
    await asyncify(_juju_wait)()

    for worker in worker_app.units:
        log('verifying worker ' + worker.entity_id)
        await retry_async_with_timeout(verify_ps_output,
                                        (worker, 'containerd'),
                                        timeout_msg="containerd ps test did not pass",
                                        timeout_insec=120)

    await worker_app.set_config({'gpu_driver': "auto"})
