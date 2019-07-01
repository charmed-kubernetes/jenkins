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
    proxy = proxy_app.units[0]


    return proxy


@log_calls_async
async def test_kube_node_conf(worker_unit, runtime):


    container_runtime_conf_worker = ""
    with NamedTemporaryFile() as fp:
        await worker_unit.scp_from(
            "/lib/systemd/system/%s.service" % runtime,
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
async def test_http_conf_existing_container_runtime(model, runtime):

    container_endpoint = "%s:%s" % (runtime, runtime)

    log('Adding container runtime to the model')
    # Add container runtimes
    # MIGHT want to await this - revisit before PR;
    # Does this await mean the model waits for the relations to finish implementing?
    # - Check docs.
    container_runtime = await model.deploy('/home/pjds/charms/builds/docker', num_units=0)
    await model.add_relation(container_endpoint, 'kubernetes-master:container-runtime')
    await model.add_relation(container_endpoint, 'kubernetes-worker:container-runtime')


    log('waiting...')
    await asyncify(_juju_wait)()
    log('Setting up proxy.')
    proxy = await setup_proxy(model)
    # Can try proxy.machine.dns_name if this fails.
    # Container runtime config should be overriden by the juju-envs.
    # If this config remains the below regex will fail.
    log('Setting proxy configuration on juju-model.')
    await model.set_config({ 'juju-http-proxy': "http://%s:3128" % proxy.public_address })
    await model.set_config({ 'juju-https-proxy': "http://%s:3128" % proxy.public_address })
    await container_runtime.set_config({'http_proxy': 'blah'})
    time.sleep(20)
    http_allow_all_conf = """
http_port 3128
acl all src 0.0.0.0/0
http_access allow all
    """

    log('Catting config into proxy conf and restarting service.')
    log("proxy: %s " % "cat '%s' > /etc/squid/forwardproxy.conf && sudo service squid restart" % http_allow_all_conf)
    # Could be overwritten by charm.. need to update or create new charm for this.
    await proxy.ssh("sudo chmod -R 777 /etc/squid")
    with NamedTemporaryFile() as squid_conf:
        with open(squid_conf.name, 'w') as fp:
            fp.write(http_allow_all_conf)
        await proxy.scp_to(squid_conf.name, '/etc/squid/forwardproxy.conf')
    await proxy.ssh("sudo service squid restart")


    log('waiting...')
    await asyncify(_juju_wait)()
    #     kubernetes_master_zero = model.applications['kubernetes-master'].units[0]
    worker_unit = model.applications['kubernetes-worker'].units[0]
    master_unit = model.applications['kubernetes-master'].units[0]
    await test_kube_node_conf(worker_unit, runtime)
    await test_kube_node_conf(master_unit, runtime)
    # test_kube_node_conf(master_unit, runtime)

    # Cleanup
    # await model.destroy()

    await asyncify(_juju_wait)()

@pytest.mark.asyncio
async def test_juju_proxy_vars(log_dir):
    controller = Controller()
    await controller.connect_current()
    cloud = await controller.get_cloud()
    if cloud is not 'localhost':
        async with UseModel() as model:
            for container_runtime in ['docker']:
                await test_http_conf_existing_container_runtime(model, container_runtime)
