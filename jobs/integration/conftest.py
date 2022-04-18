# This is a special file imported by pytest for any test file.
# Fixtures and stuff go here.

import os
import pytest
import asyncio
import uuid
import yaml
import requests
import click
from datetime import datetime
from pathlib import Path
from py.xml import html
from tempfile import NamedTemporaryFile
from juju.model import Model
from aioify import aioify
from traceback import format_exc
from .utils import (
    upgrade_charms,
    upgrade_snaps,
    arch,
    log_snap_versions,
    scp_from,
)
from .logger import log


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

    # Set when testing a different snapd/core channel
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
        help="Snap channel to install snapd/core snaps from",
    )

    # Set when performing series upgrade tests
    parser.addoption(
        "--is-series-upgrade",
        action="store_true",
        default=False,
        help="This test should perform a series upgrade",
    )


class Tools:
    """Utility class for accessing juju related tools"""

    def __init__(self, request):
        self._request = request
        self.requests = aioify(obj=requests)

    async def _load(self):
        request = self._request
        whoami, _ = await self.run("juju", "whoami", "--format=yaml")
        self.juju_user = yaml.safe_load(whoami)["user"]
        self.controller_name = request.config.getoption("--controller")
        self.model_name = request.config.getoption("--model")
        self.model_name_full = f"{self.juju_user}/{self.model_name}"
        self.k8s_model_name = f"{self.model_name}-k8s"
        self.k8s_model_name_full = f"{self.model_name_full}-k8s"
        self.series = request.config.getoption("--series")
        self.cloud = request.config.getoption("--cloud")
        self.k8s_cloud = f"{self.k8s_model_name}-cloud"
        self.connection = f"{self.controller_name}:{self.model_name_full}"
        self.k8s_connection = f"{self.controller_name}:{self.k8s_model_name_full}"
        self.is_series_upgrade = request.config.getoption("--is-series-upgrade")
        self.charm_channel = request.config.getoption("--charm-channel")

    async def run(self, cmd, *args, input=None):
        proc = await asyncio.create_subprocess_exec(
            cmd,
            *args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=os.environ.copy(),
        )

        if hasattr(input, "encode"):
            input = input.encode("utf8")

        stdout, stderr = await proc.communicate(input=input)
        if proc.returncode != 0:
            raise Exception(
                f"Problem with run command {cmd} (exit {proc.returncode}):\n"
                f"stdout:\n{stdout.decode()}\n"
                f"stderr:\n{stderr.decode()}\n"
            )
        return stdout.decode("utf8"), stderr.decode("utf8")

    async def juju_wait(self, *args, **kwargs):
        cmd = ["/snap/bin/juju-wait", "-e", self.connection, "-w"]
        if args:
            cmd.extend(args)
        if "timeout_secs" in kwargs and kwargs["timeout_secs"]:
            cmd.extend(["-t", str(kwargs["timeout_secs"])])
        return await self.run(*cmd)


@pytest.fixture(scope="module")
async def tools(request):
    tools = Tools(request)
    await tools._load()
    return tools


@pytest.fixture(scope="module")
async def model(request, tools):
    model = Model()
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
        await model.deploy("ch:charmed-kubernetes")
        await log_snap_versions(model, prefix="Before")
        await tools.juju_wait()
        for unit in model.units.values():
            if unit.dead:
                continue
            await unit.run(f"sudo snap refresh core --{snapd_channel}")
            await unit.run(f"sudo snap refresh snapd --{snapd_channel}")
        await tools.juju_wait()
        await log_snap_versions(model, prefix="After")
    yield model
    await model.disconnect()


@pytest.fixture(scope="module")
async def k8s_model(model, tools):
    master_app = model.applications["kubernetes-control-plane"]
    master_unit = master_app.units[0]
    created_k8s_cloud = False
    created_k8s_model = False
    k8s_model = None

    with NamedTemporaryFile() as f:
        await scp_from(
            master_unit, "config", f.name, tools.controller_name, tools.connection
        )
        config = Path(f.name).read_text()
    try:
        click.echo("Adding k8s cloud")
        await tools.run(
            "juju",
            "add-k8s",
            "--skip-storage",
            "-c",
            tools.controller_name,
            tools.k8s_cloud,
            input=config,
        )
        created_k8s_cloud = True
        click.echo("Adding k8s model")
        await tools.run(
            "juju",
            "add-model",
            "-c",
            tools.controller_name,
            tools.k8s_model_name,
            tools.k8s_cloud,
            "--config",
            "test-mode=true",
            "--no-switch",
        )
        created_k8s_model = True
        k8s_model = Model()
        await k8s_model.connect(tools.k8s_connection)
        yield k8s_model
    finally:
        click.echo("Cleaning up k8s model")
        try:
            if k8s_model:
                relations = [rel.id for rel in k8s_model.relations]
                for relation in relations:
                    click.echo(f"Removing relation {relation} from k8s model")
                    await tools.run(
                        "juju",
                        "remove-relation",
                        "-c",
                        tools.controller_name,
                        "--force",
                        relation,
                    )
                try:
                    offers = [
                        offer.offer_name
                        for offer in (await k8s_model.list_offers()).results
                    ]
                except TypeError:
                    # work around https://github.com/juju/python-libjuju/pull/452
                    offers = []
                app_names = list(k8s_model.applications.keys())
                click.echo("Disconnecting k8s model")
                await k8s_model.disconnect()
                for offer in offers:
                    click.echo(f"Removing offer {offer} from k8s model")
                    await tools.run(
                        "juju",
                        "remove-offer",
                        "-c",
                        tools.controller_name,
                        "--force",
                        "-y",
                        offer,
                    )
                for app in app_names:
                    click.echo(f"Removing app {app} from k8s model")
                    await tools.run(
                        "juju",
                        "remove-application",
                        "-m",
                        tools.k8s_connection,
                        "--force",
                        app,
                    )
        except Exception:
            click.echo(format_exc())
        try:
            if created_k8s_model:
                click.echo("Destroying k8s model")
                await tools.run(
                    "juju",
                    "destroy-model",
                    "--destroy-storage",
                    "--force",
                    "--no-wait",
                    "-y",
                    tools.k8s_connection,
                )
        except Exception:
            click.echo(format_exc())
        try:
            if created_k8s_cloud:
                click.echo("Removing k8s cloud")
                await tools.run(
                    "juju",
                    "remove-cloud",
                    "-c",
                    tools.controller_name,
                    tools.k8s_cloud,
                )
        except Exception:
            click.echo(format_exc())


@pytest.fixture
def system_arch():
    return arch


@pytest.fixture(autouse=True)
def skip_by_arch(request, system_arch):
    """Skip tests on specified arches"""
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
    """Skip tests if missing certain applications"""
    if request.node.get_closest_marker("skip_apps"):
        apps = request.node.get_closest_marker("skip_apps").args[0]
        is_available = any(app in model.applications for app in apps)
        if not is_available:
            pytest.skip("skipped, no matching applications found: {}".format(apps))


def _charm_name(app):
    """Resolve charm_name from juju.applications.Application"""
    cs, charm_url = "cs:", app.data["charm-url"].rpartition("-")[0]
    if charm_url.startswith(cs):
        return charm_url[len(cs) :]  # noqa: E203
    return charm_url


@pytest.fixture(autouse=True)
def skip_unless_all_charms(request, model):
    """Run tests only when specified charms are in the model."""
    marker = request.node.get_closest_marker("skip_unless_all_charms")
    if marker:
        charms = marker.args[0]
        current_charms = set(map(_charm_name, model.applications.values()))
        all_are_available = all(charm in current_charms for charm in charms)
        if not all_are_available:
            pytest.skip("skipped, not all matching charms found: {}".format(charms))


@pytest.fixture()
def apps_by_charm(model):
    """Pytest fixture to gather all apps matching a specific charm name."""

    def _apps_by_charm(charm):
        return {
            name: app
            for name, app in model.applications.items()
            if _charm_name(app) == charm
        }

    return _apps_by_charm


@pytest.fixture(autouse=True)
def skip_by_model(request, model):
    """Skips tests if model isn't referenced, ie validate-vault for only
    running tests applicable to vault
    """
    if request.node.get_closest_marker("on_model"):
        if request.node.get_closest_marker("on_model").args[0] not in model.info.name:
            pytest.skip("skipped on this model: {}".format(model.info.name))


@pytest.fixture
def log_dir(request):
    """Fixture directory for storing arbitrary test logs."""
    path = os.path.join(
        "logs", request.module.__name__, request.node.name.replace("/", "_")
    )
    os.makedirs(path, exist_ok=True)
    return path


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
async def deploy(request, tools):
    test_run_nonce = uuid.uuid4().hex[-4:]
    nonce_model = "{}-{}".format(tools.model_name, test_run_nonce)

    await tools.run(
        "juju",
        "add-model",
        "-c",
        tools.controller_name,
        nonce_model,
        tools.cloud,
        "--config",
        "test-mode=true",
    )

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


@pytest.fixture(scope="module")
async def cloud(model):
    config = await model.get_config()
    return config["type"].value


@pytest.fixture(autouse=True)
def skip_by_cloud(request, cloud):
    clouds_marker = request.node.get_closest_marker("clouds")
    if not clouds_marker:
        return
    allowed_clouds = set(clouds_marker.args[0])
    # from: juju add-cloud --help
    known_clouds = {
        # private clouds
        "lxd",
        "maas",
        "manual",
        "openstack",
        "vsphere",
        # public clouds
        "azure",
        "cloudsigma",
        "ec2",
        "gce",
        "oci",
    }
    unknown_clouds = allowed_clouds - known_clouds
    if unknown_clouds:
        nodeid = request.node.nodeid
        s = "s" if len(unknown_clouds) > 1 else ""
        unknown_clouds = ", ".join(unknown_clouds)
        raise ValueError(
            f"Unrecognized cloud{s} in marker for {nodeid}: {unknown_clouds}"
        )
    if cloud not in allowed_clouds:
        log(
            f"Skipping due to unsupported cloud: {cloud} not in [{', '.join(allowed_clouds)}]"
        )
        pytest.skip("unsupported cloud")


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
    if not hasattr(report, "description"):
        cells.insert(2, html.td(str(report.longrepr)))
    else:
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
