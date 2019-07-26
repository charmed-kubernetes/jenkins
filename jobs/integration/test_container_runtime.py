"""
Test portability of the container runtimes.
"""
import pytest

from .logger import log
from .utils import (
    _juju_wait,
    asyncify,
    retry_async_with_timeout
)


@pytest.mark.asyncio
async def test_containerd_to_docker(model):
    """
    Assume we're starting with containerd, replace
    with Docker and then revert to containerd.

    :param model: Object
    :return: None
    """
    containerd_app = model.applications['containerd']

    await containerd_app.remove()
    await asyncify(_juju_wait)(None, None, 'kubernetes-worker')
    # Block until containerd's removed, ignore `blocked` worker.

    docker_app = await model.deploy(
        'cs:~containers/docker',
        num_units=0,  # Subordinate.
        channel='edge'
    )

    await docker_app.add_relation(
        'docker',
        'kubernetes-master'
    )

    await docker_app.add_relation(
        'docker',
        'kubernetes-worker'
    )

    await asyncify(_juju_wait)()
    # If we settle, it's safe to 
    # assume Docker is now running
    # workloads.

    await docker_app.remove()
    await asyncify(_juju_wait)(None, None, 'kubernetes-worker')
    # Block until docker's removed, ignore `blocked` worker.

    containerd_app = await model.deploy(
        'cs:~containers/containerd',
        num_units=0,  # Subordinate.
        channel='edge'
    )

    await containerd_app.add_relation(
        'containerd',
        'kubernetes-master'
    )

    await containerd_app.add_relation(
        'containerd',
        'kubernetes-worker'
    )

    await asyncify(_juju_wait)()
