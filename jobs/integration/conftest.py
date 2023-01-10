# This is a special file imported by pytest for any test file.
# Fixtures and stuff go here.

import asyncio
import click
import inspect
import os
import pytest
import requests
import sh
import uuid
import yaml

from datetime import datetime
from functools import partial
from juju.model import Model
from pathlib import Path
from py.xml import html
from tempfile import NamedTemporaryFile
from traceback import format_exc
from .utils import (
    asyncify,
    upgrade_charms,
    upgrade_snaps,
    arch,
    log_snap_versions,
    scp_from,
    juju_run,
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
        self.requests = requests
        self.requests_get = asyncify(requests.get)

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

    async def run(self, cmd, *args, stdin=None):
        proc = await asyncio.create_subprocess_exec(
            cmd,
            *args,
            stdin=asyncio.subprocess.PIPE if stdin else None,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=os.environ.copy(),
        )

        if hasattr(stdin, "encode"):
            stdin = stdin.encode("utf8")

        stdout, stderr = await proc.communicate(input=stdin)
        if proc.returncode != 0:
            raise Exception(
                f"Problem with run command {cmd} (exit {proc.returncode}):\n"
                f"stdout:\n{stdout.decode()}\n"
                f"stderr:\n{stderr.decode()}\n"
            )
        return stdout.decode("utf8"), stderr.decode("utf8")

    def juju_wait(self, *args, **kwargs):
        """Run juju-wait command with provided arguments.

        if kwarg contains `m`: juju-wait is executed on a different model
        see juju-wait --help for other supported arguments
        """

        command = sh.Command("/snap/bin/juju-wait")
        if "m" not in kwargs:
            kwargs["m"] = self.connection
        debug = partial(click.echo, nl=False)
        result = command("-w", "-v", *args, **kwargs, _err=debug, _tee="err")
        stdout, stderr = result.stdout.decode("utf-8"), result.stderr.decode("utf-8")
        return stdout, stderr


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
        click.echo("Upgrading charms")
        await upgrade_charms(model, upgrade_charm_channel, tools)
        click.echo("Upgrading snaps")
        await upgrade_snaps(model, upgrade_snap_channel, tools)
    if request.config.getoption("--snapd-upgrade"):
        snapd_channel = request.config.getoption("--snapd-channel")
        await log_snap_versions(model, prefix="Before")
        for unit in model.units.values():
            if unit.dead:
                continue
            await juju_run(
                unit, f"sudo snap refresh core --{snapd_channel}", check=False
            )
            await juju_run(
                unit, f"sudo snap refresh snapd --{snapd_channel}", check=False
            )
        await log_snap_versions(model, prefix="After")
    yield model
    await model.disconnect()


@pytest.fixture(scope="module")
async def k8s_cloud(model, tools):
    kcp_app = model.applications["kubernetes-control-plane"]
    kcp_unit = kcp_app.units[0]
    created_k8s_cloud = False

    with NamedTemporaryFile(dir=Path.home() / ".local" / "share" / "juju") as f:
        await scp_from(
            kcp_unit, "config", f.name, tools.controller_name, tools.connection
        )
        try:
            click.echo("Adding k8s cloud")
            os.environ["KUBECONFIG"] = f.name
            await tools.run(
                "juju",
                "add-k8s",
                "--skip-storage",
                "-c",
                tools.controller_name,
                tools.k8s_cloud,
            )
            del os.environ["KUBECONFIG"]
            created_k8s_cloud = True
            yield tools.k8s_cloud
        finally:
            if not created_k8s_cloud:
                return
            click.echo("Removing k8s cloud")
            try:
                await tools.run(
                    "juju",
                    "remove-cloud",
                    "-c",
                    tools.controller_name,
                    tools.k8s_cloud,
                )
            except Exception:
                click.echo(format_exc())


@pytest.fixture(scope="module")
async def k8s_model(k8s_cloud, tools):
    k8s_model = None
    try:
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

        k8s_model = Model()
        await k8s_model.connect(tools.k8s_connection)
        yield k8s_model
    finally:
        if not k8s_model:
            return
        await tools.run("juju-crashdump", "-a", "config", "-m", tools.k8s_connection)
        click.echo("Cleaning up k8s model")
        try:
            for relation in k8s_model.relations:
                click.echo(f"Removing relation {relation.name} from k8s model")
                await relation.destroy()

            for name, offer in k8s_model.application_offers.items():
                click.echo(f"Removing offer {name} from k8s model")
                await offer.destroy()

            for name, app in k8s_model.applications.items():
                click.echo(f"Removing app {name} from k8s model")
                await app.destroy()

            click.echo("Disconnecting k8s model")
            await k8s_model.disconnect()

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
def skip_if_apps(request, model):
    """Skip tests if application predicate is True."""
    skip_marker = request.node.get_closest_marker("skip_if_apps")
    if not skip_marker:
        return
    predicate = skip_marker.args[0]
    apps = model.applications
    if predicate(apps):
        method = inspect.getsource(predicate).strip()
        pytest.skip(f"'{method}' was True")


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


@pytest.fixture()
async def k8s_version(model):
    masters = model.applications["kubernetes-control-plane"]
    k8s_version_str = masters.data["workload-version"]
    try:
        k8s_minor_version = tuple(int(i) for i in k8s_version_str.split(".")[:2])
    except ValueError:
        k8s_minor_version = None
    return k8s_minor_version


@pytest.fixture(autouse=True)
def skip_if_version(request, k8s_version):
    skip_marker = request.node.get_closest_marker("skip_if_version")
    if not skip_marker:
        return
    if k8s_version is None:
        pytest.skip("skipping, Couldn't determine k8s version yet.")
    version_predicate, *_ = skip_marker.args
    if version_predicate(k8s_version):
        pytest.skip(f"skipping, k8s version v{'.'.join(k8s_version)}")


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


@pytest.fixture()
async def kubeconfig(tools, model, tmp_path):
    local = Path(tmp_path) / "kubeconfig"
    k8s_cp = model.applications["kubernetes-control-plane"].units[0]
    await scp_from(k8s_cp, "config", local, None, tools.connection)
    yield local
