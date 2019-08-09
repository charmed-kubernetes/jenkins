# This is a special file imported by pytest for any test file.
# Fixtures and stuff go here.

import os
import pytest
import asyncio
import uuid
import yaml
from juju.model import Model
from .utils import (
    upgrade_charms,
    upgrade_snaps,
    _controller_from_env,
    _model_from_env,
    _cloud_from_env,
    arch,
    asyncify,
    _juju_wait,
    log_snap_versions,
)
from sh import juju

# Handle upgrades
test_charm_channel = os.environ.get("TEST_CHARM_CHANNEL", "edge")
test_snap_channel = os.environ.get("TEST_SNAP_CHANNEL")


def _is_upgrade():
    """ Return if this is an upgrade test
    """
    return bool(os.environ.get("TEST_UPGRADE", None))


def pytest_addoption(parser):
    parser.addoption(
        "--snapd-upgrade",
        action="store_true",
        default=False,
        help="run tests with upgraded snapd",
    )
    parser.addoption(
        "--connection",
        action="store",
        default=f"{_controller_from_env()}:{_model_from_env()}",
        help="Juju [controller:model] to use",
    )
    parser.addoption(
        "--cloud",
        action="store",
        default=_cloud_from_env(),
        help="Juju cloud to use",
    )
    parser.addoption(
        "--charm-channel",
        action="store",
        default="edge",
        help="Charm channel to use",
    )
    parser.addoption(
        "--bundle-channel",
        action="store",
        default="edge",
        help="Bundle channel to use",
    )
    parser.addoption(
        "--snap-channel",
        action="store",
        required=True,
        help="Snap channel to use eg 1.16/edge",
    )




@pytest.fixture(scope="module")
async def model(request, event_loop):
    event_loop.set_exception_handler(lambda l, _: l.stop())
    model = Model(event_loop)
    connection_name = request.config.getoption("--connection")
    await model.connect(connection_name)
    if _is_upgrade():
        print("Upgrading charms")
        await upgrade_charms(model, test_charm_channel)
    if test_snap_channel:
        print("Upgrading snaps")
        await upgrade_snaps(model, test_snap_channel)
    if request.config.getoption("--snapd-upgrade"):
        snapd_channel = os.environ.get("SNAPD_CHANNEL", "beta")
        cmd = f"sudo snap refresh core --{snapd_channel}"
        cloudinit_userdata = {"postruncmd": [cmd]}
        cloudinit_userdata_str = yaml.dump(cloudinit_userdata)
        await model.set_config({"cloudinit-userdata": cloudinit_userdata_str})
        await model.deploy("cs:~containers/charmed-kubernetes")
        await log_snap_versions(model, prefix="Before")
        await asyncify(_juju_wait)()
        await log_snap_versions(model, prefix="After")
    yield model
    await model.disconnect()


@pytest.fixture
def system_arch():
    return arch


@pytest.fixture(autouse=True)
def skip_by_arch(request, system_arch):
    """ Skip tests on specified arches
    """
    if request.node.get_closest_marker("skip_arch"):
        if system_arch in request.node.get_closest_marker("skip_arch").args[0]:
            pytest.skip("skipped on this arch: {}".format(system_arch))


@pytest.fixture(scope="module")
async def proxy_app(model):
    proxy_app = model.applications.get('squid-forwardproxy')

    if proxy_app is None:
        proxy_app = await model.deploy("cs:~pjds/squid-forwardproxy-testing-1")

    yield proxy_app


@pytest.fixture(autouse=True)
def skip_by_app(request, model):
    """ Skip tests if missing certain applications
    """
    if request.node.get_closest_marker("skip_apps"):
        apps = request.node.get_closest_marker("skip_apps").args[0]
        is_available = any(app in model.applications for app in apps)
        if not is_available:
            pytest.skip("skipped, no matching applications found: {}".format(apps))


@pytest.fixture(autouse=True)
def skip_by_model(request, model):
    """ Skips tests if model isn't referenced, ie validate-vault for only
    running tests applicable to vault
    """
    if request.node.get_closest_marker("skip_model"):
        if request.node.get_closest_marker("skip_model").args[0] not in model.info.name:
            pytest.skip("skipped on this model: {}".format(model.info.name))


@pytest.fixture
def log_dir(request):
    """ Fixture directory for storing arbitrary test logs. """
    path = os.path.join(
        "logs", request.module.__name__, request.node.name.replace("/", "_")
    )
    os.makedirs(path, exist_ok=True)
    return path


@pytest.fixture(scope="module")
def event_loop():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    yield loop
    loop.close()


@pytest.fixture
async def deploy():
    test_run_nonce = uuid.uuid4().hex[-4:]
    _model = "{}-{}".format(_model_from_env(), test_run_nonce)

    if _cloud_from_env():
        juju("add-model", "-c", _controller_from_env(), _model, _cloud_from_env())
    else:
        juju("add-model", "-c", _controller_from_env(), _model)
    juju(
        "model-config",
        "-m",
        "{}:{}".format(_controller_from_env(), _model),
        "test-mode=true",
    )

    _juju_model = Model()
    await _juju_model.connect("{}:{}".format(_controller_from_env(), _model))
    yield (_controller_from_env(), _juju_model)
    await _juju_model.disconnect()
    juju("destroy-model", "-y", "{}:{}".format(_controller_from_env(), _model))
