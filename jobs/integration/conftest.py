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
    arch,
    asyncify,
    _juju_wait,
    log_snap_versions,
)
from sh import juju


def pytest_addoption(parser):

    parser.addoption(
        "--controller", action="store", required=True, help="Juju controller to use"
    )

    parser.addoption("--model", action="store", required=True, help="Juju model to use")

    parser.addoption(
        "--series", action="store", required=True, default="bionic", help="Base series"
    )

    parser.addoption(
        "--cloud", action="store", default="aws/us-east-2", help="Juju cloud to use"
    )
    parser.addoption(
        "--charm-channel", action="store", default="edge", help="Charm channel to use"
    )
    parser.addoption(
        "--bundle-channel", action="store", default="edge", help="Bundle channel to use"
    )
    parser.addoption(
        "--snap-channel",
        action="store",
        required=False,
        help="Snap channel to use eg 1.16/edge",
    )

    # Set when performing upgrade tests
    parser.addoption(
        "--is-upgrade",
        action="store_true",
        default=False,
        help="This test should be run with snap and charm upgrades",
    )
    parser.addoption(
        "--upgrade-snap-channel",
        action="store",
        required=False,
        help="Snap channel to use eg 1.16/edge",
    )
    parser.addoption(
        "--upgrade-charm-channel",
        action="store",
        required=False,
        help="Charm channel to use (stable, candidate, beta, edge)",
    )

    # Set when testing a different snap core channel
    parser.addoption(
        "--snapd-upgrade",
        action="store_true",
        default=False,
        help="run tests with upgraded snapd",
    )
    parser.addoption(
        "--snapd-channel",
        action="store",
        required=False,
        default="beta",
        help="Snap channel to install snapcore from",
    )


@pytest.fixture(scope="module")
async def model(request, event_loop, connection_name):
    event_loop.set_exception_handler(lambda l, _: l.stop())
    model = Model(event_loop)
    await model.connect(connection_name)
    if request.config.getoption("--is-upgrade"):
        upgrade_snap_channel = request.config.getoption("--upgrade-snap-channel")
        upgrade_charm_channel = request.config.getoption("--upgrade-charm-channel")
        if not upgrade_snap_channel and upgrade_charm_channel:
            raise Exception(
                "Must have both snap and charm upgrade channels set to perform upgrade prior to validation test."
            )
        print("Upgrading charms")
        await upgrade_charms(model, upgrade_charm_channel)
        print("Upgrading snaps")
        await upgrade_snaps(model, upgrade_snap_channel)
    if request.config.getoption("--snapd-upgrade"):
        snapd_channel = request.config.getoption("--snapd-channel")
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


@pytest.fixture(scope="module")
async def connection_name(request):
    """ Provides the raw controller:model argument when calling juju directly and not from our existing fixtures
    """
    return f"{request.config.getoption('--controller')}:{request.config.getoption('--model')}"


@pytest.fixture(scope="module")
async def series(request):
    """ The os distribution series to deploy with
    """
    return request.config.getoption("--series")


@pytest.fixture(scope="module")
async def controller_name(request):
    """ Name of juju controller
    """
    return request.config.getoption("--controller")


@pytest.fixture(scope="module")
async def model_name(request):
    """ Name of juju model
    """
    return request.config.getoption("--model")


@pytest.fixture(scope="module")
async def cloud(request):
    """ The cloud to utilize
    """
    return request.config.getoption("--cloud")


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
    proxy_app = model.applications.get("squid-forwardproxy")

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
async def deploy(request, connection_name, controller_name, model_name, cloud):
    test_run_nonce = uuid.uuid4().hex[-4:]
    _model = "{}-{}".format(model_name, test_run_nonce)

    juju("add-model", "-c", controller_name, _model, cloud)
    juju("model-config", "-m", connection_name, "test-mode=true")

    _juju_model = Model()
    await _juju_model.connect("{}:{}".format(controller_name, _model))
    yield (controller_name, _juju_model)
    await _juju_model.disconnect()
    juju("destroy-model", "-y", "{}:{}".format(controller_name, _model))
