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
from tempfile import NamedTemporaryFile


async def setup_proxy(model):
    log('Adding proxy to the model')
    proxy_app = await model.deploy("cs:~pjds/squid-forwardproxy-testing-1")
    return proxy_app


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
        with open(fp.name, 'r') as stream:
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

CONFIG_REGEX = r"Environment=\"HTTP(S){0,1}_PROXY=([a-zA-Z]{4,5}://[0-9a-zA-Z.]*(:[0-9]{0,5}){0,1}){1,1}\""


async def test_kube_node_conf(worker_unit, runtime='docker'):
    configuration_contents = await get_contents(runtime, worker_unit)
    # Assert runtime config vals were overriden
    assert 'blah' not in configuration_contents

    # Assert http value was set
    match = re.search(
        CONFIG_REGEX,
        configuration_contents
    )
    assert match is not None


async def test_kube_node_conf_missing(worker_unit, runtime='docker'):
    configuration_contents = await get_contents(runtime, worker_unit)
    # Assert runtime config vals were overriden
    assert 'bla2h' in configuration_contents

    # Assert http value was set
    match = re.search(
        CONFIG_REGEX,
        configuration_contents
    )
    assert match is None


async def test_http_conf_existing_container_runtime(model, proxy_app):
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

    kubernetes_worker = model.applications['kubernetes-worker']
    kubernetes_master = model.applications['kubernetes-master']
    # LP: https://bugs.launchpad.net/juju/+bug/1835050
    await kubernetes_worker.set_config({'http_proxy': 'blah'})
    await kubernetes_master.set_config({'http_proxy': 'blah'})
    time.sleep(20)

    log('waiting...')
    await asyncify(_juju_wait)()
    for worker_unit in model.applications['kubernetes-worker'].units:
        await test_kube_node_conf(worker_unit)
    for master_unit in model.applications['kubernetes-master'].units:
        await test_kube_node_conf(master_unit)

    await model.set_config({
        'juju-http-proxy': ""
    })
    await model.set_config({
        'juju-https-proxy': ""
    })

    # Config key must be different
    await kubernetes_worker.set_config({'http_proxy': 'bla2h'})
    await kubernetes_master.set_config({'http_proxy': 'bla2h'})
    time.sleep(20)
    log('waiting...')
    await asyncify(_juju_wait)()

    for worker_unit in model.applications['kubernetes-worker'].units:
        await test_kube_node_conf_missing(worker_unit)
    for master_unit in model.applications['kubernetes-master'].units:
        await test_kube_node_conf_missing(master_unit)


@pytest.mark.asyncio
async def test_juju_proxy_vars(model):
    proxy_app = setup_proxy(model)
    await test_http_conf_existing_container_runtime(
        model,
        proxy_app
    )
