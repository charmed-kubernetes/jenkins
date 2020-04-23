from behave import *
from behave.api.async_step import async_run_until_complete
import asyncio
from cilib.test.utils import (
    run_until_success,
    setup_ev)

@given('we make a change to basic_auth.csv')
@async_run_until_complete
async def step_impl(context):
    model = await setup_ev()

    # Get a leader and non-leader unit to test with
    masters = model.applications["kubernetes-master"]
    # if len(masters.units) < 2:
    #     pytest.skip("Auth file propagation test requires multiple masters")

    for master in masters.units:
        if await master.is_leader_from_status():
            leader = master
        else:
            follower = master

    # Change basic_auth.csv on the leader, and get its md5sum
    leader_md5 = await run_until_success(
        leader,
        "echo test,test,test >> /root/cdk/basic_auth.csv && "
        "md5sum /root/cdk/basic_auth.csv",
    )

    # Check that md5sum on non-leader matches
    await run_until_success(
        follower, 'md5sum /root/cdk/basic_auth.csv | grep "{}"'.format(leader_md5)
    )

    # Cleanup (remove the line we added)
    await run_until_success(leader, "sed -i '$d' /root/cdk/basic_auth.csv")

@then('we make sure those changes propogate to other masters')
@async_run_until_complete
async def step_impl(context):
    assert context.failed is False
