import asyncio
import pytest
import reqw
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


# REVISIT:
JENKINS_PROXY = 'localhost:8888'
JENKINS_WORKING_DIR = '/tmp/jenkins_tests/juju_https_proxy/'
@log_calls_async
def test_http_conf_existing_container_runtime(model, runtime):

    log('Adding docker to the model')
    # Add container runtimes
    docker_runtime = await model.deploy('docker')
    # MIGHT want to await this - revisit before PR;
    # Does this await mean the model waits for the relations to finish implementing?
    # - Check docs.
    container_endpoint = "%s:%s" % (runtime, runtime)
    await model.set_config({ 'juju-http-config': JENKINS_PROXY })
    await model.add_relation(container_endpoint, 'kubernetes-worker:container-runtime')
    await model.add_relation(container_endpoint, 'kubernetes-master:container-runtime')

    log('waiting...')
    await asyncify(_juju_wait)()


    kubernetes_master_zero = model.applications['kubernetes-master'].units[0]
    kubernetes_worker_zero = model.applications['kubernetes-worker'].units[0]
    docker_service_file_loc = "%s/%s.service" % (JENKINS_WORKING_DIR, runtime)
    master_docker_conf = kubernetes_master_zero.scp_from(
        "/lib/systemd/system/{}.service" % runtime
        docker_service_file_loc
    )

    container_runtime_conf = ""
    with open(docker_service_file_loc, 'r') as fp:
        container_runtime_conf = fp.read()

    match = re.search(
        "Environment=\"HTTP(S){0,1}_PROXY=([a-zA-Z]{4,5}:\/\/[0-9a-zA-Z.]*:[0-9]{0,5}){0,1}\"",
        container_runtime_conf
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
                test_http_conf_existing_container_runtime(model, container_runtime)
