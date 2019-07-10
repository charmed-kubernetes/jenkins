import pytest
import yaml
from sh import juju
from .utils import (
    _juju_wait,
    _controller_from_env,
    _model_from_env,
    _series_from_env,
    asyncify,
)
from .validation import validate_all
from .logger import log


async def enable_proposed_on_model(model, series):
    archive = "{}-proposed".format(series)
    apt_line = "deb http://archive.ubuntu.com/ubuntu/ {} restricted main multiverse universe".format(
        archive
    )
    dest = "/etc/apt/sources.list.d/{}.list".format(archive)
    cmd = "echo %s > %s" % (apt_line, dest)
    cloudinit_userdata = {"postruncmd": [cmd]}
    cloudinit_userdata_str = yaml.dump(cloudinit_userdata)
    await model.set_config({"cloudinit-userdata": cloudinit_userdata_str})


async def log_docker_versions(model):
    log("Logging docker versions")
    for app in model.applications.values():
        for unit in app.units:
            action = await unit.run("docker --version")
            docker_version = (
                action.data["results"]["Stdout"].strip() or "Docker not installed"
            )
            log(unit.name + ": " + docker_version)


@pytest.mark.asyncio
async def test_docker_proposed(model, log_dir):
    # Enable <series>-proposed on this model
    await enable_proposed_on_model(model, _series_from_env())
    await asyncify(juju.deploy)(
        "-m",
        "{}:{}".format(_controller_from_env(), _model_from_env()),
        "cs:~containers/canonical-kubernetes",
        "--channel",
        "edge",
        "--overlay",
        "overlays/1.12-edge-{}-overlay.yaml".format(_series_from_env()),
    )
    await asyncify(_juju_wait)()

    # Run validation
    await log_docker_versions(model)  # log before run
    await validate_all(model, log_dir)
    await log_docker_versions(model)  # log after run
