# This is a special file imported by pytest for any test file.
# Fixtures and stuff go here.

import os
import pytest
import shutil
from contextlib import suppress

pytest.register_assert_rewrite('utils')
pytest.register_assert_rewrite('validation')

with suppress(FileNotFoundError):
    shutil.rmtree('logs')


@pytest.fixture
def log_dir(request):
    """ Fixture directory for storing arbitrary test logs. """
    path = os.path.join(
        'logs',
        request.module.__name__,
        request.node.name
    )
    os.makedirs(path)
    return path
