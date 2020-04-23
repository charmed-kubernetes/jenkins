from behave import *
from behave.api.async_step import async_run_until_complete
import asyncio
import click
from cilib.test.utils import (
    verify_ready,
    verify_deleted,
    retry_async_with_timeout,
    juju_wait,
    set_config_and_wait,
    setup_ev)


async def check_svc(app, enabled):
    unit = app.units[0]
    if enabled:
        await retry_async_with_timeout(
            verify_ready,
            (unit, "svc", ["metrics-server"], "-n kube-system"),
            timeout_msg="Unable to find metrics-server svc before timeout",
        )
    else:
        await retry_async_with_timeout(
            verify_deleted,
            (unit, "svc", "metrics-server", "-n kube-system"),
            timeout_msg="metrics-server svc still exists after timeout",
        )

@given('we disable/enable metrics in the charm config')
@async_run_until_complete
async def step_impl(context):
    model = await setup_ev()
    app = model.applications["kubernetes-master"]

    k8s_version_str = app.data["workload-version"]
    k8s_minor_version = tuple(int(i) for i in k8s_version_str.split(".")[:2])
    if k8s_minor_version < (1, 16):
        click.echo("skipping, k8s version v" + k8s_version_str)
        return

    config = await app.get_config()
    old_value = config["enable-metrics"]["value"]
    new_value = not old_value

    await set_config_and_wait(
        app, {"enable-metrics": str(new_value)}, timeout_secs=240
    )
    await check_svc(app, new_value)

    await set_config_and_wait(
        app, {"enable-metrics": str(old_value)}, timeout_secs=240
    )
    await check_svc(app, old_value)

@then('we make sure the metrics-server is started and stopped appropriately')
@async_run_until_complete
async def step_impl(context):
    assert context.failed is False
