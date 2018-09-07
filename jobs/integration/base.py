import inspect
import os
import uuid
from juju.controller import Controller


test_run_nonce = uuid.uuid4().hex[-4:]


class CleanModel():
    """
    Context manager that automatically connects to the defined
    controller, adds a fresh model, returns the connection to that model,
    and automatically disconnects and cleans up the model.

    The new model is also set as the current default for the controller
    connection.
    """
    def __init__(self):
        self._controller = None
        self._model = None
        self._model_uuid = None

    async def __aenter__(self):
        model_nonce = uuid.uuid4().hex[-4:]
        frame = inspect.stack()[1]
        test_name = frame.function.replace('_', '-')
        controller_name = os.environ.get('CONTROLLER', 'jenkins-ci-aws')
        self._controller = Controller()
        await self._controller.connect(controller_name)

        model_name = 'test-{}-{}-{}'.format(
            test_run_nonce,
            test_name,
            model_nonce,
        )
        self._model = await self._controller.add_model(model_name)
        await self._model.set_config({'test-mode': True})

        # save the model UUID in case test closes model
        self._model_uuid = self._model.info.uuid

        return self._model

    async def __aexit__(self, exc_type, exc, tb):
        await self._model.disconnect()
        await self._controller.destroy_model(self._model_uuid)
        await self._controller.disconnect()
