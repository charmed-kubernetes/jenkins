import asyncio
import pytest
import random
import os
from .base import (
    UseModel,
    _juju_wait
)
from .utils import asyncify
from .logger import log, log_calls_async


@log_calls_async
async def verify_kubeconfig_has_ip(model, ip):
    log('validating generated kubectl config file')
    one_master = random.choice(model.applications['kuberentes-master'].units)
    for i in range(5):
        action = await one_master.run('cat /home/ubuntu/config')
        if ip in action.results['Stdout']:
            break
        log("Unable to find virtual IP information in kubeconfig, retrying...")
        await asyncio.sleep(10)
    assert ip in action.results['Stdout']


@log_calls_async
async def verify_kubelet_uses_ip(model, ip):
    log('validating generated kubelet config files')
    for worker_unit in model.applications['kuberentes-worker'].units:
        cmd = 'cat /root/cdk/kubeconfig'
        for i in range(5):
            action = await worker_unit.run(cmd)
            if ip in action.results['Stdout']:
                break
            log("Unable to find virtual IP information in kubeconfig, retrying...")
            await asyncio.sleep(10)
        assert ip in action.results['Stdout']


@log_calls_async
async def verify_ip_valid(model, ip):
    log('validating ip {} is pingable'.format(ip))
    cmd = 'ping -c 1 {}'.format(ip)
    one_master = random.choice(model.applications['kuberentes-master'].units)
    one_worker = random.choice(model.applications['kuberentes-worker'].units)
    for unit in [one_master, one_worker]:
        action = await unit.run(cmd)
        assert ', 0% packet loss' in action.results['Stdout']


@log_calls_async
async def validate_hacluster_lb(model):
    try:
        masters = model.applications['kubernetes-master']
        k8s_version_str = masters.data['workload-version']
        k8s_minor_version = tuple(int(i) for i in k8s_version_str.split('.')[:2])
        if k8s_minor_version < (1, 14):
            log('skipping, k8s version v' + k8s_version_str)
            return

        if 'kubeapi-load-balancer' not in model.applications:
            log('skipping hacluster load balancer test, no load balancer deployed')

        lb = model.applications['kubeapi-load-balancer']
        num_lb = len(lb.units)
        if num_lb < 3:
            await lb.add_unit(3 - num_lb)

        await model.deploy('hacluster', num_units=0, series="bionic")
        await model.add_relation('hacluster:ha',
                                 'kubeapi-load-balancer:ha')
        test_ips = os.environ.get('TEST_IPS', '10.96.99.6 10.96.99.7')
        # virtual ip can change
        for ip in test_ips.split():
            log('hacluster: testing IP {}'.format(ip))
            cfg = {'ha-cluster-vip': ip}
            await lb.set_config(cfg)

            await asyncify(_juju_wait)()

            # tests:
            # kubeconfig points to virtual ip
            await verify_kubeconfig_has_ip(model, ip)
            # kubelet config points to virtual ip
            await verify_kubelet_uses_ip(model, ip)
            # virtual ip is pingable
            await verify_ip_valid(model, ip)
    finally:
        # cleanup
        if 'hacluster' in model.applications:
            await model.applications['hacluster'].destroy()


@log_calls_async
async def validate_hacluster_master(model):
    try:
        masters = model.applications['kubernetes-master']
        k8s_version_str = masters.data['workload-version']
        k8s_minor_version = tuple(int(i) for i in k8s_version_str.split('.')[:2])
        if k8s_minor_version < (1, 14):
            log('skipping, k8s version v' + k8s_version_str)
            return

        if 'kubeapi-load-balancer' in model.applications:
            log('skipping hacluster master test, load balancer deployed')

        num_masters = len(masters.units)
        if num_masters < 3:
            await masters.add_unit(3 - num_masters)

        await model.deploy('hacluster', num_units=0, series="bionic")
        await model.add_relation('hacluster:ha',
                                 'kubernetes-master:ha')
        # virtual ip can change, verify that
        for ip in ['10.0.5.6', '10.0.5.7']:
            cfg = {'ha-cluster-vip': ip}
            await model.applications['kubernetes-master'].set_config(cfg)

            await asyncify(_juju_wait)()

            # tests:
            # kubeconfig points to virtual ip
            await verify_kubeconfig_has_ip(model, ip)
            # kubelet config points to virtual ip
            await verify_kubelet_uses_ip(model, ip)
            # virtual ip is pingable
            await verify_ip_valid(model, ip)
    finally:
        # cleanup
        if 'hacluster' in model.applications:
            await model.applications['hacluster'].destroy()


@pytest.mark.asyncio
async def test_hacluster(log_dir):
    async with UseModel() as model:
        if 'kubeapi-load-balancer' in model.applications:
            await validate_hacluster_lb(model)
        else:
            await validate_hacluster_master(model)
