# This is a special file imported by pytest for any test file.
# Fixtures and stuff go here.

import asyncio
import click
import inspect
import os
import pytest
import requests
import sh
import shlex
import uuid
import yaml

from contextlib import contextmanager, asynccontextmanager
from cilib.lp import Client as LPClient
from datetime import datetime
from juju.model import Model
from pathlib import Path
from py.xml import html
from tempfile import NamedTemporaryFile
from .utils import (
    asyncify,
    upgrade_charms,
    upgrade_snaps,
    arch,
    log_snap_versions,
    juju_run,
    juju_run_action,
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

    parser.addoption(
        "--vault-unseal-command",
        action="store",
        required=False,
        default="",
        help="Command to run to unseal vault after a series upgrade",
    )

    parser.addoption(
        "--juju-ssh-proxy",
        action="store_true",
        default=False,
        help="Proxy Juju SSH and SCP commands through the Juju controller",
    )

    parser.addoption(
        "--use-existing-ceph-apps",
        action="store_true",
        default=False,
        help="Run ceph tests against existing ceph apps in the model",
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
        stdout, _ = await self.run("juju", "--version")
        ver_str = stdout.splitlines()[-1].split("-")[0]
        self.juju_version = tuple(map(int, ver_str.split(".")))
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
        self.vault_unseal_command = request.config.getoption("--vault-unseal-command")
        self.juju_ssh_proxy = request.config.getoption("--juju-ssh-proxy")
        self.use_existing_ceph_apps = request.config.getoption(
            "--use-existing-ceph-apps"
        )

    def juju_base(self, series):
        """Retrieve juju 3.1 base from series."""
        if self.juju_version < (3, 1):
            return f"--series={series}"
        mapping = {
            "bionic": "ubuntu@18.04",
            "focal": "ubuntu@20.04",
            "jammy": "ubuntu@22.04",
        }
        return f"--base={mapping[series]}"

    async def run(self, cmd: str, *args: str, stdin=None, _tee=False):
        """
        asynchronously run a command as a subprocess

        @param str cmd: path to command on filesystem
        @param str *args: arguments to the command
        @param Optional[bytes] stdin: data to pass over stdin
        @param _tee:
            False -- neither stdout nor stderr is tee'd
            True  -- stdout and stderr are both tee'd
            "out" -- stdout is tee'd to test stdout
            "err" -- stderr is tee'd to test stderr
        """
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

        stdout, stderr = bytearray(), bytearray()

        def tee(line: bytes, sink: bytearray, fd: int):
            sink += line
            write = _tee == "out" and fd == 1
            write |= _tee == "err" and fd == 2
            if write or _tee is True:
                os.write(fd, line)

        async def _read_stream(stream, callback):
            while True:
                line = await stream.read(1024)
                if line:
                    callback(line)
                else:
                    break

        async def _feed_stream(input):
            if input:
                # replicates what proc.communicate() does with stdin
                await proc._feed_stdin(input)

        await asyncio.wait(
            map(
                asyncio.create_task,
                [
                    _read_stream(proc.stdout, lambda _l: tee(_l, stdout, 1)),
                    _read_stream(proc.stderr, lambda _l: tee(_l, stderr, 2)),
                    _feed_stream(input=stdin),
                ],
            )
        )

        return_code = await proc.wait()
        if return_code != 0:
            raise Exception(
                f"Problem with run command {' '.join((cmd, *args))} (exit {return_code}):\n"
                f"stdout:\n{str(stdout, 'utf8')}\n"
                f"stderr:\n{str(stderr, 'utf8')}\n"
            )
        return str(stdout, "utf8"), str(stderr, "utf8")

    async def juju_wait(self, **kwargs):
        """Run juju-wait command with provided arguments.

        if kwargs contains `m`: juju-wait is executed on a different model
        if kwargs contains `max_wait`: a timeout value is set
        see juju-wait --help for other supported arguments
        """
        if "m" not in kwargs:
            kwargs["m"] = self.connection

        # max_wait and retry_errors are special
        # kwargs that shouldn't be hyphenated when calling `juju-wait`
        # swap the long form arg for its shortened version
        for arg, short in [("max_wait", "t"), ("retry_errors", "r")]:
            if arg in kwargs:
                kwargs[short] = kwargs.pop(arg)
        kwargs.update(dict(w=True, v=True))  # workload + verbose
        juju_wait = sh.Command("/snap/bin/juju-wait")
        command = shlex.split(str(juju_wait.bake(**kwargs)))
        return await self.run(*command, _tee="err")

    @asynccontextmanager
    async def fast_forward(
        self, model: Model, fast_interval: str = "10s", slow_interval=None
    ):
        """Temporarily speed up update-status firing rate for the current model.

        Returns an async context manager that temporarily sets update-status
        firing rate to `fast_interval`.
        If provided, when the context exits the update-status firing rate will
        be set to `slow_interval`. Otherwise, it will be set to the previous
        value.
        """
        update_interval_key = "update-status-hook-interval"
        if slow_interval:
            interval_after = slow_interval
        else:
            interval_after = (await model.get_config())[update_interval_key]

        await model.set_config({update_interval_key: fast_interval})
        yield
        await model.set_config({update_interval_key: interval_after})


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
async def k8s_cloud(kubeconfig, tools):
    clouds = await tools.run(
        "juju", "clouds", "--format", "yaml", "-c", tools.controller_name
    )
    if tools.k8s_cloud in yaml.safe_load(clouds[0]):
        yield tools.k8s_cloud
        return

    _created = False
    click.echo("Adding k8s cloud")
    try:
        await tools.run(
            "juju",
            "add-k8s",
            "--skip-storage",
            "-c",
            tools.controller_name,
            tools.k8s_cloud,
        )
        _created = True
        yield tools.k8s_cloud
    finally:
        if _created:
            click.echo("Removing k8s cloud")
            await tools.run(
                "juju",
                "remove-cloud",
                "-c",
                tools.controller_name,
                tools.k8s_cloud,
            )


@pytest.fixture(scope="module")
async def k8s_model(k8s_cloud, tools):
    _model_created = None
    try:
        click.echo("Adding k8s model")
        await tools.run(
            "juju",
            "add-model",
            "-c",
            tools.controller_name,
            tools.k8s_model_name,
            k8s_cloud,
            "--config",
            "test-mode=true",
            "--no-switch",
        )

        _model_created = Model()
        await _model_created.connect(tools.k8s_connection)
        yield _model_created
    finally:
        if _model_created:
            await tools.run(
                "juju-crashdump", "-a", "config", "-m", tools.k8s_connection
            )
            click.echo("Cleaning up k8s model")

            for relation in _model_created.relations:
                click.echo(f"Removing relation {relation.name} from k8s model")
                await relation.destroy()

            for name, offer in _model_created.application_offers.items():
                click.echo(f"Removing offer {name} from k8s model")
                await offer.destroy()

            for name, app in _model_created.applications.items():
                click.echo(f"Removing app {name} from k8s model")
                await app.destroy()

            click.echo("Disconnecting k8s model")
            await _model_created.disconnect()

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
    """Fixture directory for storing arbitrary test logs per test"""
    path = Path("logs", request.module.__name__, request.node.name.replace("/", "_"))
    path.mkdir(parents=True, exist_ok=True)
    return path


@pytest.fixture
def log_open(log_dir):
    """Fixture which provides a log file opener per test."""

    @contextmanager
    def _open(filename, **kwargs):
        path = Path(log_dir, filename)
        path.parent.mkdir(parents=True, exist_ok=True)
        if "mode" not in kwargs:
            # defaults to writing log files if mode not specified
            kwargs["mode"] = "w"
        with path.open(**kwargs) as fp:
            log(f"Logging to {path}... ")
            yield fp

    yield _open


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
def xfail_if_open_bugs(request):
    xfail_marker = request.node.get_closest_marker("xfail_if_open_bugs")
    if not xfail_marker:
        return
    bugs = xfail_marker.args
    lp = LPClient()
    try:
        lp.login()
    except ConnectionRefusedError:
        log("Cannot connect to launchpad, xfail tests may end up as failures")
        return

    for bug in bugs:
        for task in lp.bug(int(bug)).bug_tasks:
            if task.status not in ["Fix Released", "Won't Fix"]:
                reason = f"expect failure until LP#{bug} affecting '{task.bug_target_display_name}' is resolved: status='{task.status}'"
                request.node.add_marker(pytest.mark.xfail(True, reason=reason))


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


@pytest.hookimpl(optionalhook=True)
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


@pytest.fixture(scope="module")
async def kubeconfig(model):
    control_planes = model.applications["kubernetes-control-plane"].units
    (unit,) = [u for u in control_planes if await u.is_leader_from_status()]
    action = await juju_run_action(unit, "get-kubeconfig")
    # kubeconfig needs to be somewhere the juju confined snap client can access it
    path = Path.home() / ".local/share/juju"
    with NamedTemporaryFile(dir=path) as f:
        local = Path(f.name)
        local.write_text(action.results["kubeconfig"])
        os.environ["KUBECONFIG"] = str(local)
        yield local
        del os.environ["KUBECONFIG"]


@pytest.fixture(scope="module")
async def kubectl(kubeconfig):
    yield sh.kubectl.bake(kubeconfig=kubeconfig)
