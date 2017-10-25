import asyncio
import functools
import json
import logging
import os
import random
import shutil
import subprocess
import tempfile
import yaml

from asyncio_extras import async_contextmanager
from async_generator import yield_
from contextlib import contextmanager
from juju.controller import Controller
from juju.model import Model
from juju.errors import JujuError
from subprocess import check_output, check_call


# Get verbose output from libjuju
logging.basicConfig(level=logging.DEBUG)


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


async def dump_debug_log(model, log_dir):
    ''' Dumps Juju debug log to the log dir '''
    path = os.path.join(log_dir, 'debug-log')
    with open(path, 'w') as f:
        cmd = ['juju', 'debug-log', '-m', model.info.name, '--replay']
        await asyncify(subprocess.call)(cmd, stdout=f,
                                        stderr=subprocess.STDOUT)


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
        await unit.scp_from(remote_path, local_path)

    coroutines = [dump_debug_action(unit) for unit in model.units.values() if unit]
    await asyncio.wait(coroutines)


async def add_model_via_cli(controller, name, config):
    ''' Add a Juju model using the CLI.

    Workaround for https://github.com/juju/python-libjuju/issues/122
    '''
    cmd = ['juju', 'add-model', name]
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


@async_contextmanager
async def temporary_model(log_dir, timeout=7200):
    ''' Create and destroy a temporary Juju model named cdk-build-upgrade-*.

    This is an async context, to be used within an `async with` statement.
    '''
    with timeout_for_current_task(timeout):
        controller = Controller()
        await controller.connect_current()
        model_name = 'cdk-build-upgrade-%d' % random.randint(0, 10000)
        model_config = {'test-mode': True}
        model = await add_model_via_cli(controller, model_name, model_config)
        try:
            async with captured_fail_logs(model, log_dir):
                await yield_(model)
        finally:
            await model.disconnect()
            await controller.destroy_model(model.info.uuid)
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


async def deploy_e2e(model, charm_channel='stable', snap_channel=None, namespace='containers'):
    config = None if snap_channel is None else {'channel': snap_channel}
    e2e_charm = 'cs:~{}/kubernetes-e2e'.format(namespace)
    await model.deploy(e2e_charm, channel=charm_channel, config=config)
    await model.add_relation('kubernetes-e2e', 'easyrsa')
    await model.add_relation('kubernetes-e2e:kube-control', 'kubernetes-master:kube-control')
    await model.add_relation('kubernetes-e2e:kubernetes-master', 'kubernetes-master:kube-api-endpoint')
    await wait_for_ready(model)


async def upgrade_charms(model, channel):
    for app in model.applications.values():
        try:
            await app.upgrade_charm(channel=channel)
        except JujuError as e:
            if "already running charm" not in str(e):
                raise
    await wait_for_ready(model)


async def upgrade_snaps(model, channel):
    for app in ['kubernetes-master', 'kubernetes-worker', 'kubernetes-e2e']:
        app = model.applications.get(app)
        if app:
            await app.set_config({'channel': channel})
    for unit in model.applications['kubernetes-worker'].units:
        action = await unit.run_action('upgrade')
        await action.wait()
        assert action.status == 'completed'
    await wait_for_ready(model)


async def run_bundletester(namespace, log_dir, channel='stable', snap_channel=None):
    async with temporary_model(log_dir) as model:
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
