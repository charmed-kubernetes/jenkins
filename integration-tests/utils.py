import asyncio
import functools
import json
import os
import random
import shutil
import subprocess
import tempfile
import yaml
import time

from asyncio_extras import async_contextmanager
from async_generator import yield_
from contextlib import contextmanager
from juju.controller import Controller
from juju.model import Model
from juju.errors import JujuError
from logger import log_calls, log_calls_async
from subprocess import check_output, check_call


@log_calls
def dump_model_info(model, log_dir):
    ''' Dumps information about the model to the log dir '''
    data = {
        'applications': {k: v.data for k, v in model.applications.items()},
        'units': {k: v.data for k, v in model.units.items()},
        'machines': {k: v.data for k, v in model.machines.items()}
    }
    path = os.path.join(log_dir, 'model-info')
    with open(path, 'w') as f:
        json.dump(data, f, indent=2)
        f.write('\n')


@log_calls_async
async def dump_debug_log(model, log_dir):
    ''' Dumps Juju debug log to the log dir '''
    path = os.path.join(log_dir, 'debug-log')
    with open(path, 'w') as f:
        cmd = ['juju', 'debug-log', '-m', model.info.name, '--replay']
        await asyncify(subprocess.call)(cmd, stdout=f,
                                        stderr=subprocess.STDOUT)

@log_calls_async
async def dump_debug_actions(model, log_dir):
    ''' Runs debug action on all units, dumping the results to log dir '''
    result_dir = os.path.join(log_dir, 'debug-actions')
    os.mkdir(result_dir)

    async def dump_debug_action(unit):
        try:
            action = await unit.run_action('debug')
        except JujuError as e:
            if 'no actions defined on charm' in str(e) \
                    or 'not defined on unit' in str(e):
                return
            raise
        await action.wait()
        remote_path = action.data['results']['path']
        filename = unit.name.replace('/', '_') + '.tar.gz'
        local_path = os.path.join(result_dir, filename)
        await scp_from(unit, remote_path, local_path)

    coroutines = [dump_debug_action(unit) for unit in model.units.values() if unit]
    await asyncio.wait(coroutines)


@log_calls_async
async def add_model_via_cli(controller, name, config, force_cloud=''):
    ''' Add a Juju model using the CLI.

    Workaround for https://github.com/juju/python-libjuju/issues/122
    '''
    cmd = ['juju', 'add-model', name]
    if not force_cloud == '':
        cmd += [force_cloud]
    controller_name = controller.controller_name
    if controller_name:
        cmd += ['-c', controller_name]
    for k, v in config.items():
        cmd += ['--config', k + '=' + json.dumps(v)]
    await asyncify(check_call)(cmd)
    model = Model()
    if controller_name:
        await model.connect_model(controller_name + ':' + name)
    else:
        await model.connect_model(name)
    return model


@contextmanager
def timeout_for_current_task(timeout):
    ''' Create a context with a timeout.

    If the context body does not finish within the time limit, then the current
    asyncio task will be cancelled, and an asyncio.TimeoutError will be raised.
    '''
    loop = asyncio.get_event_loop()
    task = asyncio.Task.current_task()
    handle = loop.call_later(timeout, task.cancel)
    try:
        yield
    except asyncio.CancelledError:
        raise asyncio.TimeoutError('Timed out after %f seconds' % timeout)
    finally:
        handle.cancel()


@async_contextmanager
async def captured_fail_logs(model, log_dir):
    ''' Create a context that captures model info when any exception is raised.
    '''
    try:
        await yield_()
    except:
        dump_model_info(model, log_dir)
        await dump_debug_log(model, log_dir)
        await dump_debug_actions(model, log_dir)
        raise


@log_calls
def apply_profile(model_name):
    '''
    Apply the lxd profile
    Args:
        model_name: the model name

    Returns: lxc profile edit output

    '''
    here = os.path.dirname(os.path.abspath(__file__))
    profile = os.path.join(here, "templates", "lxd-profile.yaml")
    lxc_aa_profile="lxc.aa_profile"
    cmd ='lxc --version'
    version = check_output(['bash', '-c', cmd])
    if version.decode('utf-8').startswith('3.'):
        lxc_aa_profile="lxc.apparmor.profile"
    cmd ='sed -e "s/##MODEL##/{0}/" -e "s/##AA_PROFILE##/{1}/" "{2}" | ' \
         'lxc profile edit "juju-{0}"'.format(model_name, lxc_aa_profile, profile)
    return check_output(['bash', '-c', cmd])


@async_contextmanager
async def temporary_model(log_dir, timeout=14400, force_cloud=''):
    ''' Create and destroy a temporary Juju model named cdk-build-upgrade-*.

    This is an async context, to be used within an `async with` statement.
    '''
    with timeout_for_current_task(timeout):
        controller = Controller()
        await controller.connect_current()
        model_name = 'cdk-build-upgrade-%d' % random.randint(0, 10000)
        model_config = {'test-mode': True}
        model = await add_model_via_cli(controller, model_name, model_config, force_cloud)
        cloud = await controller.get_cloud()
        if cloud == 'localhost':
            await asyncify(apply_profile)(model_name)
        try:
            async with captured_fail_logs(model, log_dir):
                await yield_(model)
        finally:
            await model.disconnect()
            await controller.destroy_model(model_name)
            await controller.disconnect()


def assert_no_unit_errors(model):
    for unit in model.units.values():
        assert unit.workload_status != 'error'
        assert unit.agent_status != 'failed'
        assert unit.agent_status != 'lost'


def all_units_ready(model):
    ''' Returns True if all units are 'active' and 'idle', False otherwise. '''
    for unit in model.units.values():
        if unit.workload_status != 'active':
            return False
        if unit.agent_status != 'idle':
            return False
    return True


@log_calls_async
async def wait_for_ready(model):
    ''' Wait until all units are 'active' and 'idle'. '''
    # FIXME: We might need to wait for more than just unit status.
    #
    # Subordinate units, for example, don't come into existence until after the
    # principal unit has settled.
    #
    # If you see problems where this didn't wait long enough, it's probably
    # that.
    while not all_units_ready(model):
        assert_no_unit_errors(model)
        await asyncio.sleep(1)


@log_calls_async
async def conjureup(model, namespace, bundle, channel='stable', snap_channel=None):
    with tempfile.TemporaryDirectory() as tmpdirname:
        cmd = 'charm pull --channel=%s cs:~%s/%s %s'
        cmd %= channel, namespace, bundle, os.path.join(tmpdirname, bundle)
        cmd = cmd.split()
        await asyncify(check_call)(cmd)
        shutil.copytree(
            os.path.join('/snap/conjure-up/current/spells', bundle),
            os.path.join(tmpdirname, 'spell')
        )
        os.remove(os.path.join(tmpdirname, 'spell', 'steps', 'step-01_get-kubectl'))
        os.remove(os.path.join(tmpdirname, 'spell', 'steps', 'step-01_get-kubectl.yaml'))
        os.remove(os.path.join(tmpdirname, 'spell', 'steps', 'step-02_cluster-info'))
        os.remove(os.path.join(tmpdirname, 'spell', 'steps', 'step-02_cluster-info.yaml'))
        with open(os.path.join(tmpdirname, bundle, 'bundle.yaml')) as f:
            bundledata = yaml.load(f)
        appkey = 'services' if 'services' in bundledata else 'applications'
        master = bundledata[appkey]['kubernetes-master']
        worker = bundledata[appkey]['kubernetes-worker']
        if snap_channel is not None:
            master.setdefault('options', {})['channel'] = snap_channel
            worker.setdefault('options', {})['channel'] = snap_channel
        with open(os.path.join(tmpdirname, 'spell', 'bundle.yaml'), 'w') as f:
            yaml.dump(bundledata, f, default_flow_style=False)
        with open(os.path.join(tmpdirname, 'spell', 'metadata.yaml')) as f:
            metadata = yaml.load(f)
        del metadata['bundle-name']
        with open(os.path.join(tmpdirname, 'spell', 'metadata.yaml'), 'w') as f:
            yaml.dump(metadata, f, default_flow_style=False)
        cmd = 'juju show-controller --format=json'.split()
        controller_raw = await asyncify(check_output)(cmd)
        controller_name, controller = list(yaml.load(controller_raw).items())[0]
        cloud = controller['details']['cloud']
        cloud += '/' + controller['details']['region']
        cmd = ('conjure-up %s %s %s %s --debug --notrack --noreport' % (
            os.path.join(tmpdirname, 'spell'),
            cloud,
            controller_name,
            model.info.name
        )).split()
        await asyncify(check_call)(cmd)


@log_calls_async
async def juju_deploy(model, namespace, bundle, channel='stable', snap_channel=None):
    ''' Deploy the requested bundle. '''
    with tempfile.TemporaryDirectory() as temp_dir:
        url = 'cs:~%s/%s' % (namespace, bundle)
        bundle_dir = os.path.join(temp_dir, 'bundle')
        cmd = ['charm', 'pull', '--channel', channel, url, bundle_dir]
        await asyncify(subprocess.check_call)(cmd)
        if snap_channel:
            data_path = os.path.join(bundle_dir, 'bundle.yaml')
            with open(data_path) as f:
                data = yaml.load(f)
            for app in ['kubernetes-master', 'kubernetes-worker']:
                options = data['services'][app].setdefault('options', {})
                options['channel'] = snap_channel
            with open(data_path, 'w') as f:
                yaml.dump(data, f)
        await model.deploy(bundle_dir)
    await wait_for_ready(model)


def asyncify(f):
    ''' Convert a blocking function into a coroutine '''
    async def wrapper(*args, **kwargs):
        loop = asyncio.get_event_loop()
        partial = functools.partial(f, *args, **kwargs)
        return await loop.run_in_executor(None, partial)
    return wrapper


@log_calls_async
async def deploy_e2e(model, charm_channel='stable', snap_channel=None, namespace='containers'):
    config = None if snap_channel is None else {'channel': snap_channel}
    e2e_charm = 'cs:~{}/kubernetes-e2e'.format(namespace)
    await model.deploy(e2e_charm, channel=charm_channel, config=config)
    await model.add_relation('kubernetes-e2e', 'easyrsa')
    await model.add_relation('kubernetes-e2e:kube-control', 'kubernetes-master:kube-control')
    await model.add_relation('kubernetes-e2e:kubernetes-master', 'kubernetes-master:kube-api-endpoint')
    await wait_for_ready(model)


@log_calls_async
async def upgrade_charms(model, channel):
    for app in model.applications.values():
        try:
            await app.upgrade_charm(channel=channel)
        except JujuError as e:
            if "already running charm" not in str(e):
                raise
    await wait_for_ready(model)


@log_calls_async
async def upgrade_snaps(model, channel):
    for app_name, blocking in {'kubernetes-master': True, 'kubernetes-worker': True, 'kubernetes-e2e': False}.items():
        app = model.applications.get(app_name)
        # missing applications are simply not upgraded
        if not app:
            continue

        config = await app.get_config()
        # If there is no change in the snaps skipping the upgrade
        if channel == config['channel']['value']:
            continue

        await app.set_config({'channel': channel})

        if blocking:
            for unit in app.units:
                # wait for blocked status
                deadline = time.time() + 180
                while time.time() < deadline:
                    if (unit.workload_status == 'blocked' and
                            unit.workload_status_message == 'Needs manual upgrade, run the upgrade action'):
                        break
                    await asyncio.sleep(3)
                else:
                    raise TimeoutError(
                        'Unable to find blocked status on unit {0} - {1} {2}'.format(
                            unit.name, unit.workload_status, unit.agent_status))

                # run upgrade action
                action = await unit.run_action('upgrade')
                await action.wait()
                assert action.status == 'completed'

    # wait for upgrade to complete
    await wait_for_ready(model)


@log_calls_async
async def run_bundletester(namespace, log_dir, channel='stable', snap_channel=None, force_cloud=''):
    async with temporary_model(log_dir, force_cloud=force_cloud) as model:
        # fetch bundle
        bundle = 'canonical-kubernetes'
        url = 'cs:~%s/%s' % (namespace, bundle)
        bundle_dir = os.path.join(log_dir, bundle)
        cmd = ['charm', 'pull', url, '--channel', channel, bundle_dir]
        await asyncify(subprocess.check_call)(cmd)

        # update bundle config
        data_path = os.path.join(bundle_dir, 'bundle.yaml')
        with open(data_path, 'r') as f:
            data = yaml.load(f)
        if snap_channel:
            for app in ['kubernetes-master', 'kubernetes-worker']:
                options = data['services'][app].setdefault('options', {})
                options['channel'] = snap_channel
        data['services']['kubernetes-worker'].setdefault('options', {})['labels'] = 'mylabel=thebest'
        yaml.Dumper.ignore_aliases = lambda *args: True
        with open(data_path, 'w') as f:
            yaml.dump(data, f, default_flow_style=False)

        # run bundletester
        output_file = os.path.join(log_dir, 'bundletester.xml')
        cmd = [
            'bundletester',
            '--no-matrix', '-vF', '-l', 'DEBUG',
            '-t', bundle_dir,
            '-r', 'xml', '-o', output_file
        ]
        await asyncify(subprocess.check_call)(cmd)


@log_calls_async
async def scp_from(unit, remote_path, local_path):
    if await is_localhost():
        cmd = "juju scp {}:{} {}".format(unit.name, remote_path, local_path)
        await asyncify(subprocess.check_call)(cmd.split())
    else:
        await unit.scp_from(remote_path, local_path)


@log_calls_async
async def scp_to(local_path, unit, remote_path):
    if await is_localhost():
        cmd = "juju scp {} {}:{}".format(local_path, unit.name, remote_path)
        await asyncify(subprocess.check_call)(cmd.split())
    else:
        await unit.scp_to(local_path, remote_path)


async def is_localhost():
    controller = Controller()
    await controller.connect_current()
    cloud = await controller.get_cloud()
    await controller.disconnect()
    return cloud == 'localhost'


def default_bundles():
    loop = asyncio.get_event_loop()
    localhost = loop.run_until_complete(is_localhost())
    if localhost:
        return 'canonical-kubernetes'
    else:
        return 'canonical-kubernetes-canal,kubernetes-core'


async def retry_async_with_timeout(func, args, timeout_insec=600,
                                   timeout_msg="Timeout exceeded",
                                   retry_interval_insec=5):
    '''
    Retry a function until a timeout is exceeded. Function should
    return either True or Flase
    Args:
        func: The function to be retried
        args: Agruments of the function
        timeout_insec: What the timeout is (in seconds)
        timeout_msg: What to show in the timeout exception thrown
        retry_interval_insec: The interval between two consecutive executions

    '''
    deadline = time.time() + timeout_insec
    while time.time() < deadline:
        if await func(*args):
            break
        await asyncio.sleep(retry_interval_insec)
    else:
        raise TimeoutError(timeout_msg)
