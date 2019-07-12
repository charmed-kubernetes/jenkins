""" Tests snapd from a set snap channel to make sure no breakage occurs when they release new snapd versions
"""

import pytest
import yaml
import os
from sh import juju
from .utils import asyncify, _juju_wait, _controller_from_env, _model_from_env
from .logger import log

SNAP_CHANNEL = os.environ.get("SNAP_CHANNEL", "beta")


async def enable_snapd_on_model(model):
    cmd = f"sudo snap refresh core --{SNAP_CHANNEL}"
    cloudinit_userdata = {"postruncmd": [cmd]}
    cloudinit_userdata_str = yaml.dump(cloudinit_userdata)
    await model.set_config({"cloudinit-userdata": cloudinit_userdata_str})


async def log_snap_versions(model):
    log("Logging snap versions")
    for unit in model.units.values():
        if unit.dead:
            continue
        action = await unit.run("snap list")
        snap_versions = action.data["results"]["Stdout"].strip() or "No snaps found"
        log(unit.name + ": " + snap_versions)


@pytest.mark.asyncio
async def test_snapd(model, log_dir):
    await enable_snapd_on_model(model)
    await asyncify(juju.deploy)(
        "-m",
        "{}:{}".format(_controller_from_env(), _model_from_env()),
        "cs:~containers/charmed-kubernetes",
    )
    await asyncify(_juju_wait)()

    # Run validation
    # await log_snap_versions(model)  # log before run
    # await log_snap_versions(model)  # log after run
