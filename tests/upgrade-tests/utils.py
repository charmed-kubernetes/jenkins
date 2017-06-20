import asyncio
import json
import random
import sys
import subprocess
from asyncio_extras import async_contextmanager
from async_generator import yield_
from juju.controller import Controller
from juju.model import Model


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
    # Screw you, event loop!
    subprocess.check_call(cmd)
    model = Model()
    if controller_name:
        await model.connect_model(controller_name + ':' + name)
    else:
        await model.connect_model(name)
    return model


@async_contextmanager
async def temporary_model():
    ''' Create and destroy a temporary Juju model named cdk-build-upgrade-*.

    This is an async context, to be used within an `async with` statement.
    '''
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
    loop = asyncio.get_event_loop()
    deadline = loop.time() + 1800  # 30 minutes
    while not all_units_ready(model):
        assert_no_unit_errors(model)
        assert loop.time() < deadline
        await asyncio.sleep(1)
