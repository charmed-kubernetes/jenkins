""" Tests snapd from a set snap channel to make sure no breakage occurs when they release new snapd versions
"""

import pytest
import yaml
import os
from sh import juju
from .base import (
    UseModel,
    _juju_wait,
    _controller_from_env,
    _model_from_env
)
from .utils import asyncify
from .validation import validate_all
from .logger import log, log_calls_async

SNAP_CHANNEL = os.environ.get('SNAP_CHANNEL', 'beta')

@log_calls_async
async def enable_snapd_on_model(model):
    cmd = f'sudo snap refresh core --{SNAP_CHANNEL}'
    cloudinit_userdata = {'postruncmd': [cmd]}
    cloudinit_userdata_str = yaml.dump(cloudinit_userdata)
    await model.set_config({'cloudinit-userdata': cloudinit_userdata_str})


async def log_snap_versions(model):
    log('Logging snap versions')
    for unit in model.units.values():
        if unit.dead:
            continue
        action = await unit.run('snap list')
        snap_versions = action.data['results']['Stdout'].strip() or 'No snaps found'
        log(unit.name + ': ' + snap_versions)


@pytest.mark.asyncio
async def test_snapd(log_dir):
    async with UseModel() as model:
        await enable_snapd_on_model(model)
    await asyncify(juju.deploy)(
        '-m', '{}:{}'.format(_controller_from_env(), _model_from_env()),
        'cs:~containers/canonincal-kubernetes',
        '--channel', 'edge',
        '--overlay', 'overlays/1.13-edge-overlay.yaml')
    await asyncify(_juju_wait)()

    async with UseModel() as model:
        # Run validation
        await log_snap_versions(model)  # log before run
        await validate_all(model, log_dir)
        await log_snap_versions(model)  # log after run
