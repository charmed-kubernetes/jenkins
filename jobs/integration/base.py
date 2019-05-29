import os
import asyncio
from juju.model import Model
from sh import juju_wait



def _model_from_env():
    return os.environ.get('MODEL') or \
        'validate-{}'.format(os.environ['BUILD_NUMBER'])

def _controller_from_env():
    return os.environ.get('CONTROLLER', 'jenkins-ci-aws')

def _series_from_env():
    return os.environ.get('SERIES', 'bionic')

def _juju_wait(controller=None, model=None):
    if not controller:
        controller = _controller_from_env()
    if not model:
        model = _model_from_env()
    print("Settling...")
    juju_wait('-e', "{}:{}".format(controller, model), '-w')


class UseModel:
    """
    Context manager that connects to a controller:model and disconnects
    automatically.
    The controller and model must exist prior to use.
    """
    def __init__(self):
        self._controller_name = _controller_from_env()
        self._model_name = _model_from_env()
        self._model = None

    @property
    def model_name(self):
        return self._model_name

    @property
    def controller_name(self):
        return self._controller_name

    async def __aenter__(self):
        loop = asyncio.get_event_loop()
        loop.set_exception_handler(lambda l, _: l.stop())
        self._model = Model(loop)
        model_name = "{}:{}".format(self._controller_name,
                                    self._model_name)
        await self._model.connect(model_name)
        return self._model

    async def __aexit__(self, exc_type, exc, tb):
        await self._model.disconnect()
