# This is a special file imported by pytest for any test file.
# Fixtures and stuff go here.

import logging
import os
import pytest
import shutil
import asyncio
import uuid
from juju.model import Model

from sh import juju

pytest.register_assert_rewrite('utils')
pytest.register_assert_rewrite('validation')

shutil.rmtree('logs', ignore_errors=True)
os.mkdir('logs')
logging.basicConfig(filename='logs/python-logging', level=logging.DEBUG)

CONTROLLER = os.getenv('CONTROLLER')
MODEL = os.getenv('MODEL')
CLOUD = os.getenv('CLOUD')


@pytest.fixture
def log_dir(request):
    """ Fixture directory for storing arbitrary test logs. """
    path = os.path.join(
        'logs',
        request.module.__name__,
        request.node.name.replace('/', '_')
    )
    os.makedirs(path)
    return path


@pytest.fixture
def event_loop():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    yield loop
    loop.close()


@pytest.fixture
async def deploy():
    juju('add-model', '-c', CONTROLLER, _model, CLOUD)
    juju('model-config', '-m',
         '{}:{}'.format(CONTROLLER, _model), 'test-mode=true')

    _juju_model = Model()
    await _juju_model.connect("{}:{}".format(CONTROLLER, MODEL))
    yield (CONTROLLER, _juju_model)
    await _juju_model.disconnect()
    juju('destroy-model', '-y', '{}:{}'.format(CONTROLLER, MODEL))
