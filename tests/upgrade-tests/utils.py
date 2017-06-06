import asyncio
import random
from asyncio_extras import async_contextmanager
from async_generator import yield_
from juju.controller import Controller


@async_contextmanager
async def temporary_model():
    ''' Create and destroy a temporary Juju model named cdk-build-upgrade-*.

    This is an async context, to be used within an `async with` statement.
    '''
    controller = Controller()
    await controller.connect_current()
    model_name = 'cdk-build-upgrade-%d' % random.randint(0, 10000)
    model = await controller.add_model(model_name)
    try:
        await yield_(model)
    finally:
        await model.disconnect()
        await controller.destroy_model(model.info.uuid)
        await controller.disconnect()


def assert_no_unit_errors(model):
    for unit in model.units.values():
        assert unit.data['workload-status']['current'] != 'error'


def all_units_ready(model):
    ''' Returns True if all units are 'active' and 'idle', False otherwise. '''
    for unit in model.units.values():
        if unit.data['workload-status']['current'] != 'active':
            return False
        if unit.data['agent-status']['current'] != 'idle':
            return False
    return True


async def wait_for_ready(model):
    ''' Wait until all units are 'active' and 'idle'. '''
    # FIXME: We might need to wait for more than just unit status.
    #
    # Subordinate units, for example, don't come into existence until after the
    # principal unit has settled.
    #
    # If you see problems where this didn't wait long enough, it's probably that.
    while not all_units_ready(model):
        assert_no_unit_errors(model)
        await asyncio.sleep(1)
    assert_no_unit_errors(model)


def assert_healthy(model):
    ''' Assert that the current deployment is healthy. '''
    assert_no_unit_errors(model)
    expected_messages = {
      'kubernetes-master': 'Kubernetes master running.',
      'kubernetes-worker': 'Kubernetes worker running.'
    }
    for app, message in expected_messages.items():
        for unit in model.applications[app].units:
            assert unit.data['workload-status']['message'] == message
