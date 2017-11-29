import pytest
from utils import temporary_model, deploy_e2e
from utils import juju_deploy
from validation import validate_all
from logger import log


@pytest.mark.asyncio
async def test_docker_proposed(log_dir):
    async with temporary_model(log_dir) as model:
        await juju_deploy(model, 'containers', 'canonical-kubernetes')
        await deploy_e2e(model)

        worker_units = model.applications['kubernetes-worker'].units
        for unit in worker_units:
            log('Enabling xenial-proposed and updating docker.io on ' + unit.name)
            apt_line = 'deb http://archive.ubuntu.com/ubuntu/ xenial-proposed restricted main multiverse universe'
            dest = '/etc/apt/sources.list.d/xenial-proposed.list'
            await unit.run('echo %s > %s' % (apt_line, dest))
            await unit.run('apt update && apt install docker.io')
            action = await unit.run('docker --version')
            docker_version = action.data['results']['Stdout']
            log(unit.name + ': ' + docker_version)

        await validate_all(model, log_dir)
