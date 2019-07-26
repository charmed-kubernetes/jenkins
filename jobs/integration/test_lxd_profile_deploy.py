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
        "r"
    )
)


async def check_charm_profile_deployed(app, charm_name):
    machine = app.units[0]
    # log("app_info %s" % machine.safe_data)
    # Assume that the only profile with juju-* is
    # the one we"re looking for.
    result = subprocess.run(
        ["lxc", "profile", "list"],
        stdout=subprocess.PIPE
    )

    REGEX = r"(juju(-[a-zA-Z0-9]+)+(-[A-Za-z0-9]+)+(-[0-9])*)+"
    matches = re.findall(
        REGEX,
        result.stdout.decode("utf-8")
    )
    log("[DEBUG] match: {}".format(str(matches)))


    # Profiles can be in the form of
    # juju-MODEL-NAME
    # OR: juju-MODEL-NAME-APP
    # Find the one which contains the profile
    for profile_name in matches[0]:
        log("Checking profile for name: %s" % profile_name)
        # In 3.7 stdout=subprocess.PIPE
        # can be replaced with capture_output... :-]
        result = subprocess.run(
            ["lxc", "profile", "show", profile_name],
            stdout=subprocess.PIPE
        )
        config = result.stdout.decode("utf-8")

        loaded_yaml = yaml.load(config)

        if loaded_yaml is None:
            continue

        def trim_profile(profile):
            # Remove these keys as they differ at run time and are
            # not related to the configuration.
            profile.pop("name", None)
            profile.pop("used_by", None)
            return profile

        loaded_yaml = trim_profile(loaded_yaml)
        lxd_profile = trim_profile(LXD_PROFILE)

        log("Deployed Profile: %s" % loaded_yaml)
        log("Expected Profile: %s" % lxd_profile)
        profile_exists = loaded_yaml == lxd_profile

        if profile_exists:
            assert profile_exists
            log("profile exists")
            return

    assert False


@pytest.mark.parametrize(
    "charm_name",
    ["kubernetes-master", "kubernetes-worker"]
)
@pytest.mark.asyncio
async def test_lxd_profiles(model, charm_name):
    app = model.applications[charm_name]
    await check_charm_profile_deployed(app, charm_name)


@pytest.mark.parametrize(
    "charm_name",
    ("kubernetes-worker", "kubernetes-master")
)
@pytest.mark.asyncio
async def test_lxd_profile_upgrade(model, charm_name):
    app = model.applications[charm_name]
    log("Upgrading charm to edge channel")
    await app.upgrade_charm(channel="edge")
    time.sleep(10)
    log("Upgraded charm.")
    await asyncify(_juju_wait)()
    await check_charm_profile_deployed(app, charm_name)
