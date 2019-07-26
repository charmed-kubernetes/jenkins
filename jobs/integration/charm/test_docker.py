"""
Test Docker charm specific.
"""
import pytest

from ..logger import log
from ..utils import retry_async_with_timeout


@pytest.mark.asyncio
async def test_docker_opts(model):
    worker_app = model.applications['docker']

    async def verify_default_docker(worker, opt):
        action = await worker.run('cat /etc/default/docker')
        return opt in action.results['Stdout']

    async def verify_ps_output(worker, opt):
        action = await worker.run('ps -aux|grep dockerd')
        return opt in action.results['Stdout']

    log('validating dockerd options')

    for opt_to_test in ['--experimental', '--insecure-registry 10.0.0.1:5000']:
        await worker_app.set_config({'docker-opts': opt_to_test})
        log('set dockerd config ' + opt_to_test)

        for worker in worker_app.units:
            log('verifying worker ' + worker.entity_id)
            log(' - dockerd config')
            await retry_async_with_timeout(verify_default_docker,
                                           (worker, opt_to_test),
                                           timeout_msg="docker opt test did not pass",
                                           timeout_insec=120)
            log(' - ps output')
            await retry_async_with_timeout(verify_ps_output,
                                           (worker, opt_to_test),
                                           timeout_msg="docker ps test did not pass",
                                           timeout_insec=120)

    await worker_app.set_config({'docker-opts': ''})
