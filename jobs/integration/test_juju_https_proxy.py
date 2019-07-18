import asyncio
import pytest
import re
import os
import time
from .utils import (
    asyncify,
    verify_ready,
    verify_completed,
    verify_deleted,
    retry_async_with_timeout,
    _juju_wait
)
from .logger import log, log_calls_async
from juju.controller import Controller
from builtins import open as open_file
from tempfile import NamedTemporaryFile


def get_config_for_rt(runtime):
    return "/lib/systemd/system/docker.service" \
        if runtime.lower() == 'docker' \
        else "/etc/systemd/system/containerd.service.d/proxy.conf"


async def get_config_contents(file, unit):
    conf_contents = ""
    with NamedTemporaryFile() as fp:
        await unit.scp_from(
            file,
            fp.name
        )
        with open_file(fp.name, 'r') as stream:
            conf_contents = stream.read()
    return conf_contents


async def get_contents(runtime, worker_unit):
    runtime_conf_contents = ""
    service_file = get_config_for_rt(runtime)
    log("Catting service file: %s" % runtime)
    runtime_conf_contents = await get_config_contents(
        service_file,
        worker_unit
    )

    log("Configuration file value: %s" % runtime_conf_contents)
    return runtime_conf_contents

HTTP_S_REGEX = r"Environment=\"HTTP(S){0,1}_PROXY=([a-zA-Z]{4,5}://[0-9a-zA-Z.]*(:[0-9]{0,5}){0,1}){1,1}\""
BLAH_REGEX = r"Environment=\"HTTP(S){0,1}_PROXY={}\""


async def test_kube_node_conf(worker_unit, runtime):
    configuration_contents = await get_contents(runtime, worker_unit)
    # Assert runtime config vals were not overriden
    assert 'blah' in configuration_contents

    # Assert http value was set
    match = re.search(
        BLAH_REGEX.format('blah'),
        configuration_contents
    )
    assert match is not None


async def test_kube_node_conf_missing(worker_unit, runtime):
    configuration_contents = await get_contents(runtime, worker_unit)
    # Assert runtime config vals were overriden
    assert 'bla2h' in configuration_contents

    # Assert http value was set
    match = re.search(
        HTTP_S_REGEX,
        configuration_contents
    )
    assert match is None


async def setup_proxy(model):
    log('Adding proxy to the model')
    proxy_app = await model.deploy("cs:~pjds/squid-forwardproxy-testing-1")
    return proxy_app


async def test_http_conf_existing_container_runtime(model, runtime, proxy_app):
    container_endpoint = "%s:%s" % (runtime, runtime)
    container_runtime_env = "%s_RUNTIME_VERSION" % runtime.upper()
    container_runtime_name = 'cs:~pjds/%s-%s' % (
        runtime, os.environ[container_runtime_env]
    )
    log('Adding container runtime to the model container runtime')

    container_runtime = await model.deploy(container_runtime_name, num_units=0)

    await model.add_relation(
        container_endpoint,
        'kubernetes-master:container-runtime'
    )
    await model.add_relation(
        container_endpoint,
        'kubernetes-worker:container-runtime'
    )

    log('waiting...')
    await asyncify(_juju_wait)()

    proxy = proxy_app.units[0]

    # Container runtime config should be overriden by the juju-envs.
    # If this config remains the below regex will fail.
    log('Setting proxy configuration on juju-model.')
    await model.set_config({
        'juju-http-proxy': "http://%s:3128"
        % proxy.public_address
    })
    await model.set_config({
        'juju-https-proxy': "https://%s:3128"
        % proxy.public_address
    })
    # LP: https://bugs.launchpad.net/juju/+bug/1835050
    await container_runtime.set_config({'http_proxy': 'blah'})
    time.sleep(20)

    log('waiting...')
    await asyncify(_juju_wait)()
    for worker_unit in model.applications['kubernetes-worker'].units:
        await test_kube_node_conf(worker_unit, runtime)
    for master_unit in model.applications['kubernetes-master'].units:
        await test_kube_node_conf(master_unit, runtime)

    await model.set_config({
        'juju-http-proxy': ""
    })
    await model.set_config({
        'juju-https-proxy': ""
    })

    # Config key must be different
    await container_runtime.set_config({'http_proxy': ''})
    time.sleep(20)
    log('waiting...')
    await asyncify(_juju_wait)()

    for worker_unit in model.applications['kubernetes-worker'].units:
        await test_kube_node_conf_missing(worker_unit, runtime)
    for master_unit in model.applications['kubernetes-master'].units:
        await test_kube_node_conf_missing(master_unit, runtime)
    await container_runtime.remove_relation(
        container_endpoint,
        "kubernetes-master:container-runtime"
    )
    await container_runtime.remove_relation(
        container_endpoint,
        "kubernetes-worker:container-runtime"
    )


@pytest.mark.asyncio
async def test_juju_proxy_vars(model):
    proxy_app = await setup_proxy(model)
    proxy_app = model.applications['squid-forwardproxy']
    for container_runtime in ['docker', 'containerd']:
        await test_http_conf_existing_container_runtime(
            model,
            container_runtime,
            proxy_app
        )
