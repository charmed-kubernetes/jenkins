import pytest
import yaml
import os
from sh import juju
from .base import (
    UseModel,
    _juju_wait,
    _controller_from_env,
    _model_from_env,
)
from .utils import asyncify
from .validation import validate_all
from .logger import log, log_calls_async


@log_calls_async
async def enable_snapd_beta_on_model(model):
    cmd = 'sudo snap refresh care --beta'
    cloudinit_userdata = {'postruncmd': [cmd]}
    cloudinit_userdata_str = yaml.dump(cloudinit_userdata)
    await model.set_config({'cloudinit-userdata': cloudinit_userdata_str})


async def log_snap_versions(model):
    log('Logging snap versions')
    for app in model.applications.values():
        for unit in app.units:
            action = await unit.run('snap list')
            snap_versions = action.data['results']['Stdout'].strip() or 'No snaps found'
            log(unit.name + ': ' + snap_versions)


@pytest.mark.asyncio
async def test_snapd_beta(log_dir):
    async with UseModel() as model:
        await enable_snapd_beta_on_model(model)

        # # Deploy cdk
        # await model.deploy('cs:~containers/canonical-kubernetes',
        #                    channel='edge',
        #                    series=_series_from_env())
    await asyncify(juju.deploy)(
        '-m', '{}:{}'.format(_controller_from_env(), _model_from_env()),
        'cs:~containers/kubernetes-core',
        '--channel', 'edge',
        '--overlay', 'overlays/1.13-edge-{}-overlay.yaml'.format(_series_from_env()))
    await asyncify(_juju_wait)()

    async with UseModel() as model:
        # Run validation
        await log_snap_versions(model)  # log before run
        await validate_all(model, log_dir)
        await log_snap_versions(model)  # log after run
