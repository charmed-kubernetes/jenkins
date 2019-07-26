import asyncio
import functools
import json
import os
import subprocess
import time
import traceback

from contextlib import contextmanager
from juju.controller import Controller
from juju.errors import JujuError
from .logger import log, log_calls
from subprocess import check_output, check_call
from sh import juju_wait


def _model_from_env():
    return os.environ.get("MODEL") or "validate-{}".format(os.environ["BUILD_NUMBER"])


def _controller_from_env():
    return os.environ.get("CONTROLLER", "jenkins-ci-aws")


def _series_from_env():
    return os.environ.get("SERIES", "bionic")


def _cloud_from_env():
    return os.environ.get("CLOUD", None)


def _juju_wait(controller=None, model=None, exclude=None):
    """
    Juju wait.

    :param controller: String controller
    :param model: String model
    :param exclude: List String or String applications to exclude
    """
    if not controller:
        controller = _controller_from_env()

    if not model:
        model = _model_from_env()

    if exclude and isinstance(exclude, str):
            exclude = [exclude]

    command = ["-e", "{}:{}".format(controller, model), "-w"]

    if exclude:
        for x in exclude:
            command.extend(['-x', x])

    log("Settling...")
    juju_wait(*command)


@contextmanager
def timeout_for_current_task(timeout):
    """ Create a context with a timeout.

    If the context body does not finish within the time limit, then the current
    asyncio task will be cancelled, and an asyncio.TimeoutError will be raised.
    """
    loop = asyncio.get_event_loop()
    task = asyncio.Task.current_task()
    handle = loop.call_later(timeout, task.cancel)
    try:
        yield
    except asyncio.CancelledError:
        raise asyncio.TimeoutError("Timed out after %f seconds" % timeout)
    finally:
        handle.cancel()


@log_calls
def apply_profile(model_name):
    """
    Apply the lxd profile
    Args:
        model_name: the model name

    Returns: lxc profile edit output

    """
    here = os.path.dirname(os.path.abspath(__file__))
    profile = os.path.join(here, "templates", "lxd-profile.yaml")
    lxc_aa_profile = "lxc.aa_profile"
    cmd = "lxc --version"
    version = check_output(["bash", "-c", cmd])
    if version.decode("utf-8").startswith("3."):
        lxc_aa_profile = "lxc.apparmor.profile"
    cmd = (
        'sed -e "s/##MODEL##/{0}/" -e "s/##AA_PROFILE##/{1}/" "{2}" | '
        'sudo lxc profile edit "juju-{0}"'.format(model_name, lxc_aa_profile, profile)
    )
    return check_output(["bash", "-c", cmd])


def asyncify(f):
    """ Convert a blocking function into a coroutine """

    async def wrapper(*args, **kwargs):
        loop = asyncio.get_event_loop()
        partial = functools.partial(f, *args, **kwargs)
        return await loop.run_in_executor(None, partial)

    return wrapper


async def upgrade_charms(model, channel):

    for app in model.applications.values():
        try:
            await app.upgrade_charm(channel=channel)
        except JujuError as e:
            if "already running charm" not in str(e):
                raise
    # Only keep here until 1.13/1.14 go out of support scope
    await model.deploy("cs:~containers/docker", num_units=0, channel=channel)

    await model.applications["docker"].add_relation(
        "docker:docker", "kubernetes-worker:container-runtime"
    )

    await model.applications["docker"].add_relation(
        "docker:docker", "kubernetes-master:container-runtime"
    )

    await asyncify(_juju_wait)()

    await model.applications["docker"].remove_relation(
        "docker:docker", "kubernetes-master:container-runtime"
    )

    await model.applications["docker"].remove_relation(
        "docker:docker", "kubernetes-worker:container-runtime"
    )

    await model.applications["docker"].destroy()

    await model.deploy("cs:~containers/containerd", num_units=0, channel=channel)

    await model.applications["containerd"].add_relation(
        "containerd:containerd", "kubernetes-worker:container-runtime"
    )
    await model.applications["containerd"].add_relation(
        "containerd:containerd", "kubernetes-master:container-runtime"
    )

    await asyncify(_juju_wait)()


async def upgrade_snaps(model, channel):
    for app_name, blocking in {
        "kubernetes-master": True,
        "kubernetes-worker": True,
        "kubernetes-e2e": False,
    }.items():
        app = model.applications.get(app_name)
        # missing applications are simply not upgraded
        if not app:
            continue

        config = await app.get_config()
        # If there is no change in the snaps skipping the upgrade
        if channel == config["channel"]["value"]:
            continue

        await app.set_config({"channel": channel})

        if blocking:
            for unit in app.units:
                # wait for blocked status
                deadline = time.time() + 180
                while time.time() < deadline:
                    if (
                        unit.workload_status == "blocked"
                        and unit.workload_status_message
                        == "Needs manual upgrade, run the upgrade action"
                    ):
                        break
                    await asyncio.sleep(3)
                else:
                    raise TimeoutError(
                        "Unable to find blocked status on unit {0} - {1} {2}".format(
                            unit.name, unit.workload_status, unit.agent_status
                        )
                    )

                # run upgrade action
                action = await unit.run_action("upgrade")
                await action.wait()
                assert action.status == "completed"

    await asyncify(_juju_wait)()


async def is_localhost():
    controller = Controller()
    await controller.connect(_controller_from_env())
    cloud = await controller.get_cloud()
    await controller.disconnect()
    return cloud == "localhost"


async def scp_from(unit, remote_path, local_path):
    if await is_localhost():
        cmd = "juju scp -m {}:{} {}:{} {}".format(
            _controller_from_env(),
            _model_from_env(),
            unit.name,
            remote_path,
            local_path,
        )
        await asyncify(subprocess.check_call)(cmd.split())
    else:
        await unit.scp_from(remote_path, local_path)


async def scp_to(local_path, unit, remote_path):
    if await is_localhost():
        cmd = "juju scp -m {}:{} {} {}:{}".format(
            _controller_from_env(),
            _model_from_env(),
            local_path,
            unit.name,
            remote_path,
        )
        await asyncify(subprocess.check_call)(cmd.split())
    else:
        await unit.scp_to(local_path, remote_path)


async def retry_async_with_timeout(
    func,
    args,
    timeout_insec=600,
    timeout_msg="Timeout exceeded",
    retry_interval_insec=5,
):
    """
    Retry a function until a timeout is exceeded. Function should
    return either True or Flase
    Args:
        func: The function to be retried
        args: Agruments of the function
        timeout_insec: What the timeout is (in seconds)
        timeout_msg: What to show in the timeout exception thrown
        retry_interval_insec: The interval between two consecutive executions

    """
    deadline = time.time() + timeout_insec
    while time.time() < deadline:
        if await func(*args):
            break
        await asyncio.sleep(retry_interval_insec)
    else:
        raise TimeoutError(timeout_msg)


def arch():
    """Return the package architecture as a string."""
    architecture = check_output(["dpkg", "--print-architecture"]).rstrip()
    architecture = architecture.decode("utf-8")
    return architecture


async def disable_source_dest_check():
    path = os.path.dirname(__file__) + "/tigera/disable_source_dest_check.py"
    controller = _controller_from_env()
    model = _model_from_env()
    cmd = [path, "-m", controller + ":" + model]
    await asyncify(check_call)(cmd)


async def verify_deleted(unit, entity_type, name, extra_args=""):
    cmd = "/snap/bin/kubectl {} --output json get {}".format(extra_args, entity_type)
    output = await unit.run(cmd)
    if "error" in output.results["Stdout"]:
        # error resource type not found most likely. This can happen when the api server is
        # restarting. As such, don't assume this means we've finished the deletion
        return False
    try:
        out_list = json.loads(output.results["Stdout"])
    except json.JSONDecodeError:
        log(traceback.format_exc())
        log("WARNING: Expected json, got non-json output:")
        log(output.results["Stdout"])
        return False
    for item in out_list["items"]:
        if item["metadata"]["name"] == name:
            return False
    return True


async def find_entities(unit, entity_type, name_list, extra_args=""):
    cmd = "/snap/bin/kubectl {} --output json get {}"
    cmd = cmd.format(extra_args, entity_type)
    output = await unit.run(cmd)
    if output.results["Code"] != "0":
        # error resource type not found most likely. This can happen when the api server is
        # restarting. As such, don't assume this means ready.
        return False
    out_list = json.loads(output.results["Stdout"])
    matches = []
    for name in name_list:
        # find all entries that match this
        [matches.append(n) for n in out_list["items"] if name in n["metadata"]["name"]]
    return matches


async def verify_ready(unit, entity_type, name_list, extra_args=""):
    """
    note that name_list is a list of entities(pods, services, etc) being searched
    and that partial matches work. If you have a pod with random characters at
    the end due to being in a deploymnet, you can add just the name of the
    deployment and it will still match
    """

    matches = await find_entities(unit, entity_type, name_list, extra_args)
    if not matches:
        return False

    # now verify they are ALL ready, it isn't cool if just one is ready now
    ready = [
        n
        for n in matches
        if n["kind"] == "DaemonSet"
        or n["status"]["phase"] == "Running"
        or n["status"]["phase"] == "Active"
    ]
    if len(ready) != len(matches):
        return False

    # made it here then all the matches are ready
    return True


async def verify_completed(unit, entity_type, name_list, extra_args=""):
    """
    note that name_list is a list of entities(pods, services, etc) being searched
    and that partial matches work. If you have a pod with random characters at
    the end due to being in a deploymnet, you can add just the name of the
    deployment and it will still match
    """
    matches = await find_entities(unit, entity_type, name_list, extra_args)
    if not matches or len(matches) == 0:
        return False

    # now verify they are ALL completed - note that is in the phase 'Succeeded'
    return all([n["status"]["phase"] == "Succeeded" for n in matches])


async def log_snap_versions(model):
    log("Logging snap versions")
    for unit in model.units.values():
        if unit.dead:
            continue
        action = await unit.run("snap list")
        snap_versions = action.data["results"]["Stdout"].strip() or "No snaps found"
        log(unit.name + ": " + snap_versions)
