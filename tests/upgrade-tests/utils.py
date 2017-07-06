import os
import sys
import asyncio
import functools
import json
import random
import logging
import tempfile
import shutil
import yaml
from subprocess import check_output, check_call
from asyncio_extras import async_contextmanager
from async_generator import yield_
from contextlib import contextmanager
from juju.controller import Controller
from juju.model import Model


# Get verbose output from libjuju
logging.basicConfig(level=logging.DEBUG)


def dump_model_info(model):
    ''' Dumps information about the model to stdout '''
    data = {
        'applications': {k: v.data for k, v in model.applications.items()},
        'units': {k: v.data for k, v in model.units.items()},
        'machines': {k: v.data for k, v in model.machines.items()}
    }
    json.dump(data, sys.stdout, indent=2)


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
async def temporary_model(timeout=3600):
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
            await yield_(model)
        except:
            dump_model_info(model)
            raise
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


async def conjureup(model, namespace, bundle, channel, snap_channel=None):
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
        await asyncify(check_call(cmd))


def asyncify(f):
    ''' Convert a blocking function into a coroutine '''
    async def wrapper(*args, **kwargs):
        loop = asyncio.get_event_loop()
        partial = functools.partial(f, *args, **kwargs)
        return await loop.run_in_executor(None, partial)
    return wrapper
