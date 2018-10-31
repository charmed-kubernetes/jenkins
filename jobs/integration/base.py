import os
import asyncio
from juju.model import Model
from sh import juju_wait



def _model_from_env():
    return os.environ.get('MODEL') or \
        'validate-{}'.format(os.environ['BUILD_NUMBER'])


def _juju_wait(controller=None, model=None):
    if not controller:
        controller = os.environ.get('CONTROLLER', 'jenkins-ci-aws')
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
        self._controller_name = os.environ.get('CONTROLLER', 'jenkins-ci-aws')
        self._model_name = _model_from_env()
        self._model = None

    @property
    def model_name(self):
        return self._model_name

    @property
    def controller_name(self):
        return self._controller_name

    async def __aenter__(self):
        self._model = Model(asyncio.get_event_loop())
        model_name = "{}:{}".format(self._controller_name,
                                    self._model_name)
        await self._model.connect(model_name)
        return self._model

    async def __aexit__(self, exc_type, exc, tb):
        await self._model.disconnect()
