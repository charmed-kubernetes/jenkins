# This is a special file imported by pytest for any test file.
# Fixtures and stuff go here.

import os
import uvloop
import pytest
import asyncio
import uuid
import yaml
import requests
from datetime import datetime
from py.xml import html
from juju.model import Model
from aioify import aioify
from .utils import upgrade_charms, upgrade_snaps, arch, log_snap_versions


def pytest_addoption(parser):

    parser.addoption(
        "--controller", action="store", required=True, help="Juju controller to use"
    )

    parser.addoption("--model", action="store", required=True, help="Juju model to use")

    parser.addoption("--series", action="store", default="bionic", help="Base series")

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
    parser.addoption(
        "--addons-model",
        action="store",
        required=False,
        help="Juju k8s model for addons",
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

    # Set when performing series upgrade tests
    parser.addoption(
        "--is-series-upgrade",
        action="store_true",
        default=False,
        help="This test should perform a series upgrade",
    )


class Tools:
    """ Utility class for accessing juju related tools
    """

    def __init__(self, request):
        self.requests = aioify(obj=requests)
        self.controller_name = request.config.getoption("--controller")
        self.model_name = request.config.getoption("--model")
        self.series = request.config.getoption("--series")
        self.cloud = request.config.getoption("--cloud")
        self.connection = f"{self.controller_name}:{self.model_name}"
        self.is_series_upgrade = request.config.getoption("--is-series-upgrade")

    async def run(self, *cmd):
        proc = await asyncio.create_subprocess_shell(
            " ".join(cmd),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=os.environ.copy(),
        )

        stdout, stderr = await proc.communicate()
        if proc.returncode > 0:
            raise Exception(
                f"Problem with run command [{' '.join(cmd)}]: \nstdout: "
                f"{stdout.decode()}\nstderr: {stderr.decode()}"
            )

    async def juju_wait(self, *args, **kwargs):
        cmd = f"juju wait -e {self.connection} -w"
        if args:
            cmd = f"{cmd} {' '.join(args)}"
        if "timeout_secs" in kwargs and kwargs["timeout_secs"]:
            cmd = f"{cmd} -t {kwargs['timeout_secs']}"
        return await self.run(cmd)


@pytest.fixture(scope="module")
def tools(request):
    return Tools(request)


@pytest.fixture(scope="module")
async def model(request, event_loop, tools):
    model = Model(event_loop)
    await model.connect(tools.connection)
    if request.config.getoption("--is-upgrade"):
        upgrade_snap_channel = request.config.getoption("--upgrade-snap-channel")
        upgrade_charm_channel = request.config.getoption("--upgrade-charm-channel")
        if not upgrade_snap_channel and upgrade_charm_channel:
            raise Exception(
                "Must have both snap and charm upgrade "
                "channels set to perform upgrade prior to validation test."
            )
        print("Upgrading charms")
        await upgrade_charms(model, upgrade_charm_channel, tools)
        print("Upgrading snaps")
        await upgrade_snaps(model, upgrade_snap_channel, tools)
    if request.config.getoption("--snapd-upgrade"):
        snapd_channel = request.config.getoption("--snapd-channel")
        cmd = f"sudo snap refresh core --{snapd_channel}"
        cloudinit_userdata = {"postruncmd": [cmd]}
        cloudinit_userdata_str = yaml.dump(cloudinit_userdata)
        await model.set_config({"cloudinit-userdata": cloudinit_userdata_str})
        await model.deploy("cs:~containers/charmed-kubernetes")
        await log_snap_versions(model, prefix="Before")
        await tools.juju_wait()
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
    if request.node.get_closest_marker("on_model"):
        if request.node.get_closest_marker("on_model").args[0] not in model.info.name:
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
    uvloop.install()
    loop = asyncio.new_event_loop()
    assert isinstance(loop, uvloop.Loop)
    yield loop
    # loop.close()


@pytest.fixture
async def deploy(request, tools):
    test_run_nonce = uuid.uuid4().hex[-4:]
    nonce_model = "{}-{}".format(tools.model_name, test_run_nonce)

    await tools.run(
        "juju", "add-model", "-c", tools.controller_name, nonce_model, tools.cloud
    )

    await tools.run("juju", "model-config", "-m", tools.connection, "test-mode=true")

    _model_obj = Model()
    await _model_obj.connect(f"{tools.controller_name}:{nonce_model}")
    yield (tools.controller_name, _model_obj)
    await _model_obj.disconnect()
    await tools.run("juju", "destroy-model", "-y", nonce_model)


@pytest.fixture(scope="module")
async def addons_model(request):
    controller_name = request.config.getoption("--controller")
    model_name = request.config.getoption("--addons-model")
    if not model_name:
        pytest.skip("--addons-model not specified")
        return
    model = Model()
    await model.connect(controller_name + ":" + model_name)
    yield model
    await model.disconnect()


@pytest.fixture
def cloud(request):
    cloud_name = request.config.getoption("--cloud")
    return cloud_name.split("/")[0]


@pytest.fixture(autouse=True)
def skip_by_cloud(request, cloud):
    clouds_marker = request.node.get_closest_marker("clouds")
    if clouds_marker and cloud not in clouds_marker.args[0]:
        pytest.skip("skipped on this cloud: {}".format(cloud))


# def pytest_itemcollected(item):
#     par = item.parent.obj
#     node = item.obj
#     pref = par.__doc__.strip() if par.__doc__ else par.__class__.__name__
#     suf = node.__doc__.strip() if node.__doc__ else node.__name__
#     if pref or suf:
#         item._nodeid = ' '.join((pref, suf))


def pytest_html_report_title(report):
    report.title = "Validation Result"


def pytest_html_results_table_header(cells):
    cells.insert(2, html.th("Description"))
    cells.insert(1, html.th("Time", class_="sortable time", col="time"))
    cells.pop()


def pytest_html_results_table_row(report, cells):
    cells.insert(2, html.td(report.description))
    cells.insert(1, html.td(datetime.utcnow(), class_="col-time"))
    cells.pop()


@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    report = outcome.get_result()
    report.description = str(item.function.__doc__)
    # we only look at actual failing test calls, not setup/teardown
    if report.when == "call" and report.failed:
        mode = "a" if os.path.exists("failures") else "w"
        with open("failures", mode) as f:
            f.write(report.longreprtext + "\n")


@pytest.mark.optionalhook
def pytest_metadata(metadata):
    custom_name = os.environ.get("JOB_NAME_CUSTOM", None)
    if custom_name:
        metadata["JOB_NAME"] = custom_name
        metadata[
            "ARTIFACTS"
        ] = f"<a href='http://jenkaas.s3-website-us-east-1.amazonaws.com/{os.environ['JOB_ID']}/artifacts.tar.gz'>Download Artifacts</a>"
        metadata[
            "ANALYTICS"
        ] = f"<a href='http://jenkaas.s3-website-us-east-1.amazonaws.com/{os.environ['JOB_ID']}/columbo.html'>View Report</a>"
