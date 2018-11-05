import os
import pytest
import subprocess
import yaml
from .base import UseModel, _model_from_env, _controller_from_env
from utils import temporary_model, deploy_e2e
from utils import juju_deploy, asyncify
from validation import validate_all
from logger import log


async def enable_proposed_on(target, series='bionic'):
    log('Enabling {}-proposed on {}'.format(series, target))
    apt_line = 'deb http://archive.ubuntu.com/ubuntu/ {}-proposed restricted main multiverse universe'.format(series)
    apt_source_list = '/etc/apt/sources.list.d/{}-proposed.list'.format(series)
    remote_cmd = 'echo %s | sudo tee %s && sudo apt update' % (apt_line, apt_source_list)
    cmd = ['juju', 'ssh', '-m',
           '{}:{}'.format(_controller_from_env(), _model_from_env()),
           target, remote_cmd]
    while True:
        log("Running " + str(cmd))
        code = await asyncify(subprocess.call)(cmd)
        if code == 0:
            break


async def log_docker_versions(model):
    app = model.applications['kubernetes-worker']
    for unit in app.units:
        action = await unit.run('docker --version')
        docker_version = action.data['results']['Stdout']
        log(unit.name + ': ' + docker_version)


@pytest.mark.asyncio
async def test_docker_proposed(log_dir):
    async with UseModel() as model:
        # Deploy bundle with 0 worker units
        url = 'cs:~containers/canonical-kubernetes'
        bundle_dir = os.path.join(log_dir, 'bundle')
        cmd = ['charm', 'pull', url, bundle_dir]
        await asyncify(subprocess.check_call)(cmd)
        data_path = os.path.join(bundle_dir, 'bundle.yaml')
        with open(data_path) as f:
            data = yaml.load(f)
        data['services']['kubernetes-worker']['num_units'] = 0
        with open(data_path, 'w') as f:
            yaml.dump(data, f)
        await model.deploy(bundle_dir)

        # Add worker machine with series enabled
        constraints_str = data['services']['kubernetes-worker']['constraints']
        # I don't feel like writing a constraint parser right now
        assert constraints_str == 'cores=4 mem=4G', "Test assumption is no longer true"
        constraints = {'cores': 4, 'mem': 4 * 1024}
        machine = await model.add_machine(constraints=constraints)
        await enable_proposed_on(machine.id)

        # Add worker unit to machine
        app = model.applications['kubernetes-worker']
        await app.add_unit(to=machine.id)

        # Now do the usual.
        await log_docker_versions(model)
        await validate_all(model, log_dir)


@pytest.mark.asyncio
async def test_docker_proposed_upgrade(log_dir):
    async with UseModel() as model:
        await juju_deploy(model, 'containers', 'canonical-kubernetes')

        worker_units = model.applications['kubernetes-worker'].units
        for unit in worker_units:
            log('Enabling {}-proposed and updating docker.io on {}'.format(series, unit.name))
            await enable_proposed_on(unit.name)
            await unit.run('apt install docker.io')

        await log_docker_versions(model)
        await validate_all(model, log_dir)
