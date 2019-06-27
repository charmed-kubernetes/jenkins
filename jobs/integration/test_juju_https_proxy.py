import asyncio
import pytest
import re
import os
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

# REVISIT:
JENKINS_PROXY =  os.environ.get('http_proxy')
@log_calls_async
async def test_http_conf_existing_container_runtime(model, runtime):

    log('Adding container-runtime to the model')
    await model.set_config({ 'juju-http-config': "http://192.168.2.103:8888" })
    # Add container runtimes
    # container_runtime = await model.deploy('cs:~containers/%s-0' % runtime, num_units=0)
    container_runtime = await model.deploy('/home/pjds/charms/builds/docker', num_units=0)
    # proxy = await model.deploy('cs:haproxy-52', num_units=1)


    # Container runtime config should be overriden by the juju-envs.
    # If this config remains the below regex will fail.
    container_runtime.set_config({'http_proxy': 'blah'})
    # MIGHT want to await this - revisit before PR;
    # Does this await mean the model waits for the relations to finish implementing?
    # - Check docs.
    container_endpoint = "%s:%s" % (runtime, runtime)

    await model.add_relation(container_endpoint, 'kubernetes-worker:container-runtime')
    await model.add_relation(container_endpoint, 'kubernetes-master:container-runtime')

    log('waiting...')
    await asyncify(_juju_wait)()


    kubernetes_master_zero = model.applications['kubernetes-master'].units[0]
    kubernetes_worker_zero = model.applications['kubernetes-worker'].units[0]
    # await kubernetes_master_zero.scp_from(
    #     "/lib/systemd/system/%s.service.master" % runtime,
    #     docker_service_file_loc
    # )
    container_runtime_conf_worker = ""
    with NamedTemporaryFile() as fp:
        await kubernetes_worker_zero.scp_from(
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

    # Cleanup
    await model.destroy()

    await asyncify(_juju_wait)()

@pytest.mark.asyncio
async def test_juju_proxy_vars(log_dir):
    controller = Controller()
    await controller.connect_current()
    cloud = await controller.get_cloud()
    if cloud is not 'localhost':
        async with UseModel() as model:
            for container_runtime in ['docker', 'containerd']:
                await test_http_conf_existing_container_runtime(model, container_runtime)
