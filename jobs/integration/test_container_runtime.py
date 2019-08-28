"""
Test portability of the container runtimes.
"""
import pytest


@pytest.mark.asyncio
async def test_containerd_to_docker(model, tools):
    """
    Assume we're starting with containerd, replace
    with Docker and then revert to containerd.

    :param model: Object
    :return: None
    """
    containerd_app = model.applications["containerd"]

    await containerd_app.remove()
    await tools.juju_wait("-x", "kubernetes-worker")
    # Block until containerd's removed, ignore `blocked` worker.

    docker_app = await model.deploy(
        "cs:~containers/docker", num_units=0, channel="edge"  # Subordinate.
    )

    await docker_app.add_relation("docker", "kubernetes-master")

    await docker_app.add_relation("docker", "kubernetes-worker")

    await tools.juju_wait()
    # If we settle, it's safe to
    # assume Docker is now running
    # workloads.

    await docker_app.remove()
    await tools.juju_wait("-x", "kubernetes-worker")
    # Block until docker's removed, ignore `blocked` worker.

    containerd_app = await model.deploy(
        "cs:~containers/containerd", num_units=0, channel="edge"  # Subordinate.
    )

    await containerd_app.add_relation("containerd", "kubernetes-master")

    await containerd_app.add_relation("containerd", "kubernetes-worker")

    await tools.juju_wait()
