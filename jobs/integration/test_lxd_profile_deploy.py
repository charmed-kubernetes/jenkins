import asyncio
import pytest
import subprocess
import yaml
import time
import os
import re
from .utils import (
    asyncify,
    verify_ready,
    verify_completed,
    verify_deleted,
    retry_async_with_timeout,
    _juju_wait
)
from .logger import log, log_calls_async
from juju.controller import Controller
from juju.errors import JujuError
here = os.path.dirname(os.path.abspath(__file__))

LXD_PROFILE = yaml.load(
    open(
        os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "templates",
            "lxd-profile.yaml"
        ),
        'r'
    )
)


async def check_charm_profile_deployed(app, charm_name):
    machine = app.units[0]
    log('app_info %s' % machine.safe_data)
    # Assume that the only profile with juju-* is
    # the one we're looking for.
    result = subprocess.run(
        ['lxc', 'profile', 'list'],
        stdout=subprocess.PIPE
    )
    model_name = "NO-MODEL"
    for profile_line in result.stdout.decode('utf-8').split('\n'):
        match = re.search(
            r"juju-(([a-zA-Z0-9])+-)*{}-[a-zA-Z0-9]+".format(
                charm_name.split('-')[-1]
            ),
            profile_line
        )
        if match is not None:
            model_name = match.group()
            break

    log('Checking profile for name: %s' % model_name)
    # In 3.7 stdout=subprocess.PIPE
    # can be replaced with capture_output... :-]
    result = subprocess.run(
        ['lxc', 'profile', 'show', model_name],
        stdout=subprocess.PIPE
    )

    config = result.stdout.decode('utf-8')

    loaded_yaml = yaml.load(config)

    # Remove these keys as they differ at run time and are
    # not related to the configuration.
    loaded_yaml.pop("name", None)
    loaded_yaml.pop("used_by", None)

    log('Deployed Profile: %s' % loaded_yaml)
    log('Expected Profile: %s' % LXD_PROFILE)
    assert loaded_yaml == LXD_PROFILE


async def test_lxd_profile_deployed(model, charm_names, channel):
    for name in charm_names:
        app = model.applications[name]
        await check_charm_profile_deployed(app, name)


async def test_lxd_profile_deployed_upgrade(model, charm_names, channel):
    for name in charm_names:
        app = model.applications[name]
        log('Upgrading charm to edge channel')
        await app.upgrade_charm(channel=channel)
        time.sleep(10)
        log('Upgraded charm.')
        await asyncify(_juju_wait)()
        await check_charm_profile_deployed(app, name)


@pytest.mark.asyncio
async def test_lxd_profiles(model):
    await test_lxd_profile_deployed(
        model,
        ['kubernetes-worker', 'kubernetes-master'],
        os.environ['CHARM_UPGRADE_CHANNEL']
    )


@pytest.mark.asyncio
async def test_lxd_profile_upgrade(model):
    await test_lxd_profile_deployed_upgrade(
        model,
        ['kubernetes-worker', 'kubernetes-master'],
        os.environ['CHARM_UPGRADE_CHANNEL']
    )
