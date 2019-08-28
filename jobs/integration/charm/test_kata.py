"""
Test Kata untrusted container runtimes.
"""
import pytest


@pytest.mark.asyncio
async def test_kata(model, tools):
    """
    Deploy Kata, wait for it to
    stabelize and then remove.

    :param model: Object
    :return: None
    """
    kata_app = await model.deploy(
        "cs:~containers/kata", num_units=0, channel="edge"  # Subordinate.
    )

    await kata_app.add_relation(
        "kata:containerd", "kubernetes-master:container-runtime"
    )

    await kata_app.add_relation(
        "kata:containerd", "kubernetes-worker:container-runtime"
    )

    await kata_app.add_relation("kata:untrusted", "containerd:untrusted")

    await tools.juju_wait()

    # To test this further, we'd need to deploy the kata charm
    # to an i3.metal instance.  These are very expensive, so not
    # sure if we want to do that out of the box.  If we do decide
    # to, just deploy a dummy container as `untrusted` and check it
    # finishes.

    await kata_app.remove()
    await tools.juju_wait()
