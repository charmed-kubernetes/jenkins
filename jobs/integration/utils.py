import asyncio
import functools
import ipaddress
import json
import os
import shutil
import subprocess
import time
import traceback
from pathlib import Path

from contextlib import contextmanager
from typing import Mapping, Any, Union, Sequence

from juju.unit import Unit
from juju.controller import Controller
from juju.machine import Machine
from juju.errors import JujuError
from juju.utils import block_until_with_coroutine
from tempfile import TemporaryDirectory
from subprocess import check_output, check_call
from cilib import log
import click


# note: we can't upgrade to focal until after it's released
SERIES_ORDER = [
    "bionic",
    "focal",
    "jammy",
]


def tracefunc(frame, event, arg):
    if event != "call":
        return

    package_name = __name__.split(".")[0]

    if package_name in str(frame):
        co = frame.f_code
        func_name = co.co_name
        if func_name == "write":
            # Ignore write() calls from print statements
            return
        func_line_no = frame.f_lineno
        func_filename = co.co_filename
        if "conftest" in func_filename:
            return
        log.debug(f"Call to {func_name} on line {func_line_no}:{func_filename}")
        for i in range(frame.f_code.co_argcount):
            name = frame.f_code.co_varnames[i]
            log.debug(f"    Argument {name} is {frame.f_locals[name]}")
    return


@contextmanager
def timeout_for_current_task(timeout):
    """Create a context with a timeout.

    If the context body does not finish within the time limit, then the current
    asyncio task will be cancelled, and an asyncio.TimeoutError will be raised.
    """
    loop = asyncio.get_event_loop()
    task = asyncio.current_task()
    handle = loop.call_later(timeout, task.cancel)
    try:
        yield
    except asyncio.CancelledError:
        raise asyncio.TimeoutError("Timed out after %f seconds" % timeout)
    finally:
        handle.cancel()


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
    """Convert a blocking function into a coroutine"""

    async def wrapper(*args, **kwargs):
        loop = asyncio.get_event_loop()
        partial = functools.partial(f, *args, **kwargs)
        return await loop.run_in_executor(None, partial)

    return wrapper


async def upgrade_charms(model, channel, tools):
    model_name = model.info.name
    for app in model.applications.values():
        await tools.run(
            "juju", "upgrade-charm", "-m", model_name, app.name, "--channel", channel
        )
        # Blocked on https://github.com/juju/python-libjuju/issues/728
        # try:
        #    await app.upgrade_charm(channel=channel)
        # except JujuError as e:
        #     if "already running charm" not in str(e):
        #         raise
    await tools.juju_wait()


async def upgrade_snaps(model, channel, tools):
    for app_name, blocking in {
        "kubernetes-control-plane": True,
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
                    raise asyncio.TimeoutError(
                        "Unable to find blocked status on unit {0} - {1} {2}".format(
                            unit.name, unit.workload_status, unit.agent_status
                        )
                    )

                # run upgrade action
                await juju_run_action(unit, "upgrade")

    await tools.juju_wait()


async def is_localhost(controller_name):
    controller = Controller()
    await controller.connect(controller_name)
    cloud = await controller.get_cloud()
    await controller.disconnect()
    return cloud == "localhost"


async def scp_from(unit, remote_path, local_path, controller_name, connection_name):
    """Carefully scp from juju units to the local filesystem through a temporary directory."""
    local_path = Path(local_path)
    with TemporaryDirectory(dir=Path.home() / ".local" / "share" / "juju") as tmpdir:
        temp_path = Path(tmpdir) / local_path.name
        cmd = "juju scp -m {} {}:{} {}".format(
            connection_name, unit.name, remote_path, temp_path
        )
        await asyncify(subprocess.check_call)(cmd.split())
        shutil.copy(temp_path, local_path)


async def scp_to(local_path, unit, remote_path, controller_name, connection_name):
    """Carefully scp from the local filesystem to juju units through a temporary directory."""
    local_path = Path(local_path)
    with TemporaryDirectory(dir=Path.home() / ".local" / "share" / "juju") as tmpdir:
        temp_path = Path(tmpdir) / local_path.name
        shutil.copy(local_path, temp_path)
        cmd = "juju scp -m {} {} {}:{}".format(
            connection_name, temp_path, unit.name, remote_path
        )
        await asyncify(subprocess.check_call)(cmd.split())


async def retry_async_with_timeout(
    func,
    args,
    kwds=None,
    timeout_insec=600,
    timeout_msg="Timeout exceeded",
    retry_interval_insec=5,
):
    """
    Retry a function until a timeout is exceeded. If retry is
    desired, the function should return something falsey
    Args:
        func: The function to be retried
        args: Agruments of the function
        timeout_insec: What the timeout is (in seconds)
        timeout_msg: What to show in the timeout exception thrown
        retry_interval_insec: The interval between two consecutive executions

    """
    deadline = time.time() + timeout_insec
    results = None
    while time.time() < deadline:
        if results := await func(*args, **(kwds or {})):
            return results
        await asyncio.sleep(retry_interval_insec)
    else:
        raise asyncio.TimeoutError(timeout_msg.format(results))


def arch():
    """Return the package architecture as a string."""
    architecture = check_output(["dpkg", "--print-architecture"]).rstrip()
    architecture = architecture.decode("utf-8")
    return architecture


async def disable_source_dest_check(model_name):
    path = os.path.dirname(__file__) + "/tigera_aws.py"
    env = os.environ.copy()
    env["JUJU_MODEL"] = model_name
    cmd = [path, "disable-source-dest-check"]
    await asyncify(check_call)(cmd, env=env)


async def verify_deleted(unit, entity_type, name_list, extra_args=""):
    matches = await find_entities(unit, entity_type, name_list, extra_args)

    # An empty match list means we didn't find any entities with our name(s).
    # That's good since we are verifying those entities were deleted.
    if matches == []:
        return True

    # Otherwise, find_entities failed or found matches; that's bad either way.
    return False


async def find_entities(unit, entity_type, name_list, extra_args=""):
    cmd = "/snap/bin/kubectl --kubeconfig /root/.kube/config {} --output json get {}"
    cmd = cmd.format(extra_args, entity_type)
    output = await juju_run(unit, cmd)
    if output.code != 0:
        # error resource type not found most likely. This can happen when the
        # api server is restarting. As such, don't assume this means ready.
        return False
    try:
        out_list = json.loads(output.stdout)
    except json.JSONDecodeError:
        click.echo(traceback.format_exc())
        click.echo("WARNING: Expected json, got non-json output:")
        click.echo(output.results.get("Stdout", ""))
        return False
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
    # separate matches into ready and not ready
    def separate(result, n):
        idx = int(
            n["kind"] == "DaemonSet"
            or n["kind"] == "Service"
            or n["status"]["phase"] == "Running"
            or n["status"]["phase"] == "Active"
        )
        # no match, put in the left bucket
        # yes match, put in the right bucket
        result[idx].append(n)
        return result

    not_ready, ready = functools.reduce(separate, matches, ([], []))
    if len(ready) != len(matches):
        for n in not_ready:
            kind = n["kind"]
            name, ns = (
                n["metadata"]["name"],
                n["metadata"].get("namespace"),
            )
            log.info(f"Not yet ready: {kind}/{ns}/{name}")
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


async def log_snap_versions(model, prefix="before"):
    click.echo("Logging snap versions")
    for unit in model.units.values():
        if unit.dead:
            continue
        action = await juju_run(unit, "snap list")
        snap_versions = action.stdout.strip() or "No snaps found"
        click.echo(f"{prefix} {unit.name} {snap_versions}")


async def validate_storage_class(model, sc_name, test_name):
    control_plane = model.applications["kubernetes-control-plane"].units[0]
    # write a string to a file on the pvc
    pod_definition = """
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: {0}-pvc
  annotations:
   volume.beta.kubernetes.io/storage-class: {0}
spec:
  accessModes:
  - ReadWriteOnce
  resources:
    requests:
      storage: 1Gi
---
kind: Pod
apiVersion: v1
metadata:
  name: {0}-write-test
spec:
  volumes:
  - name: shared-data
    persistentVolumeClaim:
      claimName: {0}-pvc
      readOnly: false
  containers:
    - name: {0}-write-test
      image: rocks.canonical.com/cdk/ubuntu:focal
      command: ["/bin/bash", "-c", "echo 'JUJU TEST' > /data/juju"]
      volumeMounts:
      - name: shared-data
        mountPath: /data
  restartPolicy: Never
""".format(
        sc_name
    )
    cmd = "/snap/bin/kubectl --kubeconfig /root/.kube/config create -f - << EOF{}EOF".format(
        pod_definition
    )
    click.echo("{}: {} writing test".format(test_name, sc_name))
    output = await juju_run(control_plane, cmd)
    assert output.status == "completed"

    # wait for completion
    await retry_async_with_timeout(
        verify_completed,
        (control_plane, "po", ["{}-write-test".format(sc_name)]),
        timeout_msg="Unable to create write pod for {} test".format(test_name),
    )

    # read that string from pvc
    pod_definition = """
kind: Pod
apiVersion: v1
metadata:
  name: {0}-read-test
spec:
  volumes:
  - name: shared-data
    persistentVolumeClaim:
      claimName: {0}-pvc
      readOnly: false
  containers:
    - name: {0}-read-test
      image: rocks.canonical.com/cdk/ubuntu:focal
      command: ["/bin/bash", "-c", "cat /data/juju"]
      volumeMounts:
      - name: shared-data
        mountPath: /data
  restartPolicy: Never
""".format(
        sc_name
    )
    cmd = "/snap/bin/kubectl --kubeconfig /root/.kube/config create -f - << EOF{}EOF".format(
        pod_definition
    )
    click.echo("{}: {} reading test".format(test_name, sc_name))
    output = await juju_run(control_plane, cmd)
    assert output.status == "completed"

    # wait for completion
    await retry_async_with_timeout(
        verify_completed,
        (control_plane, "po", ["{}-read-test".format(sc_name)]),
        timeout_msg="Unable to create write" " pod for ceph test",
    )

    output = await juju_run(
        control_plane,
        "/snap/bin/kubectl --kubeconfig /root/.kube/config logs {}-read-test".format(
            sc_name
        ),
    )
    assert output.status == "completed"
    click.echo("output = {}".format(output.stdout))
    assert "JUJU TEST" in output.stdout

    click.echo("{}: {} cleanup".format(test_name, sc_name))
    pods = "{0}-read-test {0}-write-test".format(sc_name)
    pvcs = "{}-pvc".format(sc_name)
    output = await juju_run(
        control_plane,
        "/snap/bin/kubectl --kubeconfig /root/.kube/config delete po {}".format(pods),
    )
    assert output.status == "completed"
    output = await juju_run(
        control_plane,
        "/snap/bin/kubectl --kubeconfig /root/.kube/config delete pvc {}".format(pvcs),
    )
    assert output.status == "completed"

    await retry_async_with_timeout(
        verify_deleted,
        (control_plane, "po", pods.split()),
        timeout_msg="Unable to remove {} test pods".format(test_name),
    )
    await retry_async_with_timeout(
        verify_deleted,
        (control_plane, "pvc", pvcs.split()),
        timeout_msg="Unable to remove {} test pvcs".format(test_name),
    )


def _units(machine: Machine):
    return [
        unit for unit in machine.model.units.values() if unit.machine.id == machine.id
    ]


async def wait_for_status(workload_status: str, units: Union[Unit, Sequence[Unit]]):
    """
    Wait for unit or units to reach a specific workload_state or fail in 120s.
    """
    if not isinstance(units, (list, tuple)):
        units = [units]
    log.info(
        f'waiting for {workload_status} status on {", ".join(u.name for u in units)}'
    )
    model = units[0].model
    try:
        await model.block_until(
            lambda: all(unit.workload_status == workload_status for unit in units),
            timeout=120,
        )
    except asyncio.TimeoutError as e:
        unmatched_units = [
            f"{unit.name}={unit.workload_status}"
            for unit in units
            if unit.workload_status != workload_status
        ]
        raise AssertionError(
            f'Units with unexpected status: {",".join(unmatched_units)}'
        ) from e


async def wait_for_application_status(model, app_name, status="active"):
    async def check_app_status():
        apps = await model.get_status()
        app = apps.applications[app_name]
        return app.status.status == status

    try:
        await block_until_with_coroutine(check_app_status, timeout=120)
    except asyncio.TimeoutError:
        apps = await model.get_status()
        app = apps.applications[app_name]
        raise AssertionError(f"Application has unexpected status: {app.status.status}")


async def prep_series_upgrade(machine, new_series, tools):
    log.info(f"preparing series upgrade for machine {machine.id}")
    await tools.run(
        "juju",
        "upgrade-series",
        "--yes",
        "-m",
        tools.connection,
        machine.id,
        "prepare",
        new_series,
    )
    await wait_for_status("blocked", _units(machine))


async def do_series_upgrade(machine):
    file_name = "/etc/apt/apt.conf.d/50unattended-upgrades"
    option = "--force-confdef"
    log.info(f"doing series upgrade for machine {machine.id}")
    await machine.ssh(
        f"""
        if ! grep -q -- '{option}' {file_name}; then
          echo 'DPkg::options {{ "{option}"; }};' | sudo tee -a {file_name}
        fi
        sudo DEBIAN_FRONTEND=noninteractive do-release-upgrade -f DistUpgradeViewNonInteractive
    """
    )
    log.info(f"rebooting machine {machine.id}")
    try:
        await machine.ssh("sudo reboot && exit")
    except JujuError:
        # We actually expect this to "fail" because the reboot closes the session prematurely.
        pass


async def finish_series_upgrade(machine, tools):
    log.info(f"completing series upgrade for machine {machine.id}")
    await tools.run(
        "juju",
        "upgrade-series",
        "--yes",
        "-m",
        tools.connection,
        machine.id,
        "complete",
    )
    await wait_for_status("active", _units(machine))


class JujuRunError(AssertionError):
    def __init__(self, unit, command, result):
        self.unit = unit
        self.command = command
        self.code = result.code
        self.stdout = result.stdout
        self.stderr = result.stderr
        self.output = result.output
        super().__init__(
            f"`{self.command}` failed on {self.unit.name}:\n{self.stdout}\n{self.stderr}"
        )


class JujuRunResult:
    def __init__(self, action):
        self._action = action

    @property
    def status(self) -> str:
        return self._action.status

    @property
    def results(self) -> Mapping[str, Any]:
        return self._action.results

    @property
    def code(self) -> str:
        code = self.results.get("Code", self.results.get("return-code"))
        if code is None:
            log.error(f"Failed to find the return code in {self.results}")
            return -1
        return int(code)

    @property
    def stdout(self) -> str:
        stdout = self.results.get("Stdout", self.results.get("stdout")) or ""
        return stdout.strip()

    @property
    def stderr(self) -> str:
        stderr = self.results.get("Stderr", self.results.get("stderr")) or ""
        return stderr.strip()

    @property
    def output(self) -> str:
        return self.stderr or self.stdout

    @property
    def success(self) -> bool:
        return self.status == "completed" and self.code == 0

    def __repr__(self) -> str:
        return f"JujuRunResult({self._action})"


async def juju_run(unit, cmd, check=True, **kwargs) -> JujuRunResult:
    action = await unit.run(cmd, **kwargs)
    action = await action.wait()
    result = JujuRunResult(action)
    if check and not result.success:
        raise JujuRunError(unit, cmd, result)
    return result


async def juju_run_retry(
    unit: Unit, cmd: str, tries: int, delay: int = 5, **kwargs
) -> JujuRunResult:
    """Retry the command on a unit until either success or maximum number of tries.

    @param int tries: number of times to execute juju_run before returning a failed action.
    @param int delay: number of seconds to wait between retries after a failed action.
    """
    retries = 0
    while retries == 0 or retries < tries:
        retries += 1
        action = await juju_run(unit, cmd, check=False, **kwargs)
        if action.success:
            break
        else:
            click.echo(
                "Action " + action.status + ". Command failed on unit " + unit.entity_id
            )
            click.echo(f"cmd: {cmd}")
            click.echo(f"code: {action.code}")
            click.echo(f"stdout:\n{action.stdout}")
            click.echo(f"stderr:\n{action.stderr}")
            click.echo("Will retry...")
            await asyncio.sleep(delay)
    return action


async def juju_run_action(unit, action, _check=True, **kwargs) -> JujuRunResult:
    action = await unit.run_action(action, **kwargs)
    action = await action.wait()
    result = JujuRunResult(action)
    if _check and not result.success:
        raise JujuRunError(unit, action, result)
    return result


async def kubectl(model, cmd, check=True):
    control_plane = model.applications["kubernetes-control-plane"].units[0]
    return await juju_run(
        control_plane, f"/snap/bin/kubectl --kubeconfig /root/.kube/config {cmd}", check
    )


async def _kubectl_doc(document, model, action):
    if action not in ["apply", "delete"]:
        raise ValueError(f"Invalid action {action}")

    control_plane = model.applications["kubernetes-control-plane"].units[0]
    remote_path = f"/tmp/{document.name}"
    await scp_to(
        document,
        control_plane,
        remote_path,
        None,
        model.info.uuid,
    )
    cmd = f"{action} -f {remote_path}"
    return await kubectl(model, cmd)


async def kubectl_apply(document, model):
    return await _kubectl_doc(document, model, "apply")


async def kubectl_delete(document, model):
    return await _kubectl_doc(document, model, "delete")


async def vault(unit, cmd, **env):
    env[
        "VAULT_FORMAT"
    ] = "json"  # Can't override this or we won't be able to parse the results
    env.setdefault("VAULT_ADDR", "http://localhost:8200")
    env = " ".join(f"{key}='{value}'" for key, value in env.items())
    result = await juju_run(unit, f"{env} /snap/bin/vault {cmd}")
    return json.loads(result.stdout)


async def vault_status(unit):
    try:
        click.echo(f"Checking Vault status on {unit.name}")
        result = await vault(unit, "status")
    except JujuRunError as e:
        if e.code == 2:
            # This just means Vault is sealed, which is fine.
            result = json.loads(e.stdout)
        else:
            click.echo(f"Vault not running on {unit.name}: {e.output}")
            return None
    click.echo(f"Vault is running on {unit.name}: {result}")
    return result


async def get_ipv6_addr(unit):
    """Return the first globally scoped IPv6 address found on the given unit, or None."""
    output = await juju_run(unit, "ip -br a show scope global")
    for intf in output.results["Stdout"].splitlines():
        if "UP" not in intf:
            continue
        for addr in intf.split("  ")[-1].split():
            addr = ipaddress.ip_interface(addr).ip
            if addr.version == 6:
                return str(addr)
    return None


async def get_svc_ingress(model, svc_name, timeout=2 * 60):
    log.info(f"Waiting for ingress address for {svc_name}")
    for attempt in range(timeout >> 2):
        result = await kubectl(
            model,
            f"get svc {svc_name} -o jsonpath={{.status.loadBalancer.ingress[0].ip}}",
        )
        assert result.code == 0
        ingress_address = result.stdout
        log.info(f"Ingress address: {ingress_address}")
        if ingress_address != "":
            return ingress_address
        else:
            await asyncio.sleep(2)
    else:
        raise TimeoutError(
            f"Timed out waiting for {svc_name} to have an ingress address"
        )
