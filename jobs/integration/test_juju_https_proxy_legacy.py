import asyncio
import pytest
import re
import os
import time
from .base import (
    UseModel,
    _juju_wait
)
from .utils import (
    asyncify,
    verify_ready,
    verify_completed,
    verify_deleted,
    retry_async_with_timeout
)
from .logger import log, log_calls_async
from juju.controller import Controller
from builtins import open as open_file
from tempfile import NamedTemporaryFile

async def setup_proxy(model):
    log('Adding proxy to the model')
    proxy_app = await model.deploy("cs:~pjds/squid-forwardproxy-testing-1")
    log('waiting...')
    await asyncify(_juju_wait)()
    proxy_app = model.applications['squid-forwardproxy']

    return proxy_app


@log_calls_async
async def test_kube_node_conf(worker_unit):
    container_runtime_conf_worker = ""
    with NamedTemporaryFile() as fp:
        await worker_unit.scp_from(
            "/lib/systemd/system/docker.service",
            fp.name
        )
        with open_file(fp.name, 'r') as stream:
            container_runtime_conf_worker = stream.read()


    log("Configuration file value: %s" % container_runtime_conf_worker)

    # Assert runtime config vals were overriden
    assert 'blah' not in container_runtime_conf_worker

    # Assert http value was set
    match = re.search(
        "Environment=\"HTTP(S){0,1}_PROXY=([a-zA-Z]{4,5}:\/\/[0-9a-zA-Z.]*:[0-9]{0,5}){0,1}\"",
        container_runtime_conf_worker
    )
    assert match is not None


@log_calls_async
async def test_http_conf_existing_container_runtime(model):

    log('waiting...')
    await asyncify(_juju_wait)()
    log('Setting up proxy.')
    proxy_app = await setup_proxy(model)
    proxy = proxy_app.units[0]
    kubernetes_worker_app = model.applications['kubernetes-worker']
    kubernetes_master_app = model.applications['kubernetes-master']
    # Container runtime config should be overriden by the juju-envs.
    # If this config remains the below regex will fail.
    log('Setting proxy configuration on juju-model.')
    await model.set_config({ 'juju-http-proxy': "http://%s:3128" % proxy.public_address })
    await model.set_config({ 'juju-https-proxy': "https://%s:3128" % proxy.public_address })
    await kubernetes_worker_app.set_config({'http_proxy': 'blah'})
    await kubernetes_master_app.set_config({'http_proxy': 'blah'})
    time.sleep(20)

########## Try this out. The charm should by default be OK to use.
#     http_allow_all_conf = """
# http_port 3128
# acl all src 0.0.0.0/0
# http_access allow all
# """
#     log('Catting config into proxy conf and restarting service.')
#     log("proxy: %s " % "cat '%s' > /etc/squid/forwardproxy.conf && sudo service squid restart" % http_allow_all_conf)
#     # Could be overwritten by charm.. need to update or create new charm for this.
#     await proxy.ssh("sudo chmod -R 777 /etc/squid")
#     with NamedTemporaryFile() as squid_conf:
#         with open(squid_conf.name, 'w') as fp:
#             fp.write(http_allow_all_conf)
#         await proxy.scp_to(squid_conf.name, '/etc/squid/forwardproxy.conf')
#     await proxy.ssh("sudo service squid restart")


    log('waiting...')
    await asyncify(_juju_wait)()

    for worker_unit in model.applications['kubernetes-worker'].units:
        await test_kube_node_conf(worker_unit)
    for worker_unit in model.applications['kubernetes-master'].units:
        await test_kube_node_conf(worker_unit)

    # # Cleanup
    # await controller.destroy_model()
    await proxy.remove()

    log('waiting...')
    await asyncify(_juju_wait)()

@pytest.mark.asyncio
async def test_juju_proxy_vars(log_dir):
    controller = Controller()
    await controller.connect_current()
    cloud = await controller.get_cloud()
    if cloud is not 'localhost':
        async with UseModel() as model:
            await test_http_conf_existing_container_runtime(model)
    await controller.destroy_model(model.info.uuid)
