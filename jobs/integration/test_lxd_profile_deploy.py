import pytest
import sh
import yaml
import time
import os
import re
from .logger import log

here = os.path.dirname(os.path.abspath(__file__))

LXD_PROFILE = yaml.load(
    open(
        os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "templates", "lxd-profile.yaml"
        ),
        "r",
    )
)


async def check_charm_profile_deployed(app, charm_name):
    # log("app_info %s" % machine.safe_data)
    # Assume that the only profile with juju-* is
    # the one we"re looking for.
    result = sh.lxc.profile.list()

    REGEX = r"(juju(-[a-zA-Z0-9]+)+(-[A-Za-z0-9]+)+(-[0-9])*)+"
    matches = re.findall(REGEX, result)
    log("[DEBUG] match: {}".format(str(matches)))

    # Profiles can be in the form of
    # juju-MODEL-NAME
    # OR: juju-MODEL-NAME-APP
    # Find the one which contains the profile
    for profile_name in matches[0]:
        log("Checking profile for name: %s" % profile_name)
        config = sh.lxc.profile.show(profile_name)
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
    "charm_name", ["kubernetes-control-plane", "kubernetes-worker"]
)
async def test_lxd_profiles(model, charm_name):
    app = model.applications[charm_name]
    await check_charm_profile_deployed(app, charm_name)


@pytest.mark.parametrize(
    "charm_name", ("kubernetes-worker", "kubernetes-control-plane")
)
async def test_lxd_profile_upgrade(model, charm_name, tools):
    app = model.applications[charm_name]
    log("Upgrading charm to edge channel")
    await app.upgrade_charm(channel="edge")
    time.sleep(10)
    log("Upgraded charm.")
    await tools.juju_wait()
    await check_charm_profile_deployed(app, charm_name)
