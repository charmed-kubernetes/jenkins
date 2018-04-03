import asyncio
import json
import os
import requests
import time
import traceback
import yaml
import re

from logger import log, log_calls, log_calls_async
from tempfile import NamedTemporaryFile
from utils import assert_no_unit_errors, asyncify, wait_for_ready
from utils import timeout_for_current_task, scp_from, scp_to, is_localhost


@log_calls_async
async def validate_all(model, log_dir):
    validate_status_messages(model)
    await validate_snap_versions(model)
    await validate_microbot(model)
    await validate_dashboard(model, log_dir)
    await validate_kubelet_anonymous_auth_disabled(model)
    await validate_rbac_flag(model)
    await validate_rbac(model)
    await validate_e2e_tests(model, log_dir)
    await validate_worker_master_removal(model)
    await validate_sans(model)
    if "canal" in model.applications:
        log("Running canal specific tests")
        await validate_network_policies(model)
    await validate_extra_args(model)
    await validate_docker_logins(model)
    assert_no_unit_errors(model)


@log_calls
def validate_status_messages(model):
    ''' Validate that the status messages are correct. '''
    expected_messages = {
        'kubernetes-master': 'Kubernetes master running.',
        'kubernetes-worker': 'Kubernetes worker running.',
        'kubernetes-e2e': 'Ready to test.'
    }
    for app, message in expected_messages.items():
        for unit in model.applications[app].units:
            assert unit.workload_status_message == message


@log_calls_async
async def validate_snap_versions(model):
    ''' Validate that the installed snap versions are consistent with channel
    config on the charms.
    '''
    snaps_to_validate = {
        'kubernetes-master': [
            'kubectl',
            'kube-apiserver',
            'kube-controller-manager',
            'kube-scheduler',
            'cdk-addons',
        ],
        'kubernetes-worker': [
            'kubectl',
            'kubelet',
            'kube-proxy',
        ],
    }
    for app_name, snaps in snaps_to_validate.items():
        app = model.applications[app_name]
        config = await app.get_config()
        channel = config['channel']['value']
        if '/' not in channel:
            message = 'validate_snap_versions: skipping %s, channel=%s'
            message = message % (app_name, channel)
            log(message)
            continue
        track = channel.split('/')[0]
        for unit in app.units:
            action = await unit.run('snap list')
            assert action.status == 'completed'
            raw_output = action.data['results']['Stdout']
            # Example of the `snap list` output format we're expecting:
            # Name        Version  Rev   Developer  Notes
            # conjure-up  2.1.5    352   canonical  classic
            # core        16-2     1689  canonical  -
            # kubectl     1.6.2    27    canonical  classic
            lines = raw_output.splitlines()[1:]
            snap_versions = dict(line.split()[:2] for line in lines)
            for snap in snaps:
                snap_version = snap_versions[snap]
                assert snap_version.startswith(track + '.')


@log_calls_async
async def validate_rbac(model):
    ''' Validate RBAC is actually on '''
    app = model.applications['kubernetes-master']
    await app.set_config({'authorization-mode': 'RBAC,Node'})
    await wait_for_process(model, 'RBAC')
    cmd = "/snap/bin/kubectl --kubeconfig /root/cdk/kubeconfig get clusterroles"
    worker = model.applications['kubernetes-worker'].units[0]
    output = await worker.run(cmd)
    assert output.status == 'completed'
    assert "forbidden" in output.data['results']['Stderr'].lower()
    await app.set_config({'authorization-mode': 'AlwaysAllow'})
    await wait_for_process(model, 'AlwaysAllow')
    output = await worker.run(cmd)
    assert output.status == 'completed'
    assert "forbidden" not in output.data['results']['Stderr']


@log_calls_async
async def validate_rbac_flag(model):
    ''' Switch between auth modes and check the apiserver follows '''
    master = model.applications['kubernetes-master']
    await master.set_config({'authorization-mode': 'RBAC'})
    await wait_for_process(model, 'RBAC')
    await master.set_config({'authorization-mode': 'AlwaysAllow'})
    await wait_for_process(model, 'AlwaysAllow')


@log_calls_async
async def wait_for_process(model, arg):
    ''' Retry api_server_with_arg <checks> times with a 5 sec interval '''
    checks = 10
    ready = False
    while not ready:
        checks -= 1
        if await api_server_with_arg(model, arg):
            return
        else:
            if checks <= 0:
                assert False
            await asyncio.sleep(5)


async def api_server_with_arg(model, argument):
    master = model.applications['kubernetes-master']
    for unit in master.units:
        search = 'ps -ef | grep {} | grep apiserver'.format(argument)
        action = await unit.run(search)
        assert action.status == 'completed'
        raw_output = action.data['results']['Stdout']
        return len(raw_output.splitlines()) == 1
    return False


@log_calls_async
async def validate_microbot(model):
    ''' Validate the microbot action '''
    unit = model.applications['kubernetes-worker'].units[0]
    action = await unit.run_action('microbot', delete=True)
    await action.wait()
    action = await unit.run_action('microbot', replicas=3)
    await action.wait()
    assert action.status == 'completed'
    for i in range(60):
        try:
            resp = await asyncify(requests.get)('http://' + action.data['results']['address'])
            if resp.status_code == 200:
                return
        except requests.exceptions.ConnectionError:
            log("Caught connection error attempting to hit xip.io, retrying. Error follows:")
            traceback.print_exc()
        await asyncio.sleep(1)
    raise MicrobotError('Microbot failed to start.')


@log_calls_async
async def validate_dashboard(model, log_dir):
    ''' Validate that the dashboard is operational '''
    unit = model.applications['kubernetes-master'].units[0]
    with NamedTemporaryFile() as f:
        await scp_from(unit, 'config', f.name)
        with open(f.name, 'r') as stream:
            config = yaml.load(stream)
    url = config['clusters'][0]['cluster']['server']
    user = config['users'][0]['user']['username']
    password = config['users'][0]['user']['password']
    auth = requests.auth.HTTPBasicAuth(user, password)
    resp = await asyncify(requests.get)(url, auth=auth, verify=False)
    assert resp.status_code == 200
    # get k8s version
    app_config = await model.applications['kubernetes-master'].get_config()
    channel = app_config['channel']['value']
    version_string = channel.split('/')[0]
    k8s_version = tuple(int(q) for q in re.findall("[0-9]+", version_string)[:2])
    # dashboard will present a login form prompting for login
    if (k8s_version < (1, 8)):
        url = '%s/api/v1/namespaces/kube-system/services/kubernetes-dashboard/proxy/#!/login'
    else:
        url = '%s/api/v1/namespaces/kube-system/services/https:kubernetes-dashboard:/proxy/#!/login'
    url %= config['clusters'][0]['cluster']['server']
    resp = await asyncify(requests.get)(url, auth=auth, verify=False)
    assert resp.status_code == 200
    assert "Dashboard" in resp.text


@log_calls_async
async def validate_kubelet_anonymous_auth_disabled(model):
    ''' Validate that kubelet has anonymous auth disabled '''
    @log_calls_async
    async def validate_unit(unit):
        await unit.run('open-port 10250')
        address = unit.public_address
        url = 'https://%s:10250/pods/' % address
        response = await asyncify(requests.get)(url, verify=False)
        assert response.status_code == 401  # Unauthorized
    units = model.applications['kubernetes-worker'].units
    await asyncio.gather(*(validate_unit(unit) for unit in units))


@log_calls_async
async def validate_e2e_tests(model, log_dir):
    ''' Validate that the e2e tests pass.'''
    masters = model.applications['kubernetes-master']
    await masters.set_config({'allow-privileged': 'true'})
    workers = model.applications['kubernetes-worker']
    await workers.set_config({'allow-privileged': 'true'})
    if len(workers.units) < 2:
        await workers.add_unit(1)
    await wait_for_ready(model)

    e2e_unit = model.applications['kubernetes-e2e'].units[0]

    attempts = 0

    while attempts < 3:
        attempts += 1
        if await is_localhost():
            # add HostPath test to the already skipped tests
            action = await e2e_unit.run_action('test', skip='Flaky|Serial|HostPath')
        else:
            action = await e2e_unit.run_action('test')
        await action.wait()
        for suffix in ['.log', '-junit.tar.gz']:
            src = action.entity_id + suffix
            dest = os.path.join(log_dir, 'e2e-%d' % attempts + suffix)
            await scp_from(e2e_unit, src, dest)
        if action.status == 'completed':
            break
        else:
            log("Attempt %d/3 failed." % attempts)

    assert action.status == 'completed'


async def verify_deleted(unit, entity_type, name, extra_args=''):
    cmd = "/snap/bin/kubectl {} --output json get {}".format(extra_args, entity_type)
    output = await unit.run(cmd)
    out_list = json.loads(output.results['Stdout'])
    for item in out_list['items']:
        if item['metadata']['name'] == name:
            return False
    return True


async def verify_ready(unit, entity_type, name_list, extra_args=''):
    cmd = "/snap/bin/kubectl {} --output json get {}".format(extra_args, entity_type)
    output = await unit.run(cmd)
    out_list = json.loads(output.results['Stdout'])
    found_names = 0
    for item in out_list['items']:
        if item['metadata']['name'] in name_list:
            if item['status']['phase'] == 'Running' or item['status']['phase'] == 'Active':
                found_names += 1
            else:
                return False
    return found_names == len(name_list)


@log_calls_async
async def validate_network_policies(model):
    ''' Apply network policy and use two busyboxes to validate it. '''
    here = os.path.dirname(os.path.abspath(__file__))
    unit = model.applications['kubernetes-master'].units[0]

    # Clean-up namespace from any previous runs.
    cmd = await unit.run('/snap/bin/kubectl delete ns netpolicy')
    assert cmd.status == 'completed'
    log('Waiting for pods to finish terminating...')
    deadline = time.time() + 600
    while time.time() < deadline:
        if await verify_deleted(unit, 'ns', 'netpolicy'):
            break
        await asyncio.sleep(5)
    else:
        raise TimeoutError('Unable to remove the namespace netpolicy before timeout')

    # Move manifests to the master
    await scp_to(os.path.join(here, "templates", "netpolicy-test.yaml"), unit, "netpolicy-test.yaml")
    await scp_to(os.path.join(here, "templates", "restrict.yaml"), unit, "restrict.yaml")
    cmd = await unit.run('/snap/bin/kubectl create -f /home/ubuntu/netpolicy-test.yaml')
    assert cmd.status == 'completed' and cmd.results['Code'] == '0'
    log('Waiting for pods to show up...')
    deadline = time.time() + 600
    while time.time() < deadline:
        if await verify_ready(unit, 'po', ['bboxgood','bboxbad'], '-n netpolicy'):
            break
        await asyncio.sleep(5)
    else:
        raise TimeoutError('Unable to create pods for network policy test')

    # Try to get to nginx from both busyboxes.
    # We expect no failures since we have not applied the policy yet.
    query_from_bad="/snap/bin/kubectl exec bboxbad -n netpolicy -- wget --timeout=3  nginx.netpolicy"
    query_from_good = "/snap/bin/kubectl exec bboxgood -n netpolicy -- wget --timeout=3  nginx.netpolicy"
    cmd = await unit.run(query_from_good)
    assert cmd.status == 'completed'
    assert "index.html" in cmd.data['results']['Stderr']
    cmd = await unit.run(query_from_bad)
    assert cmd.status == 'completed'
    assert "index.html" in cmd.data['results']['Stderr']

    # Apply network policy and retry getting to nginx.
    # This time the policy should block us.
    cmd = await unit.run('/snap/bin/kubectl create -f /home/ubuntu/restrict.yaml')
    assert cmd.status == 'completed'
    await asyncio.sleep(10)
    query_from_bad="/snap/bin/kubectl exec bboxbad -n netpolicy -- wget --timeout=3  nginx.netpolicy -O foo.html"
    query_from_good = "/snap/bin/kubectl exec bboxgood -n netpolicy -- wget --timeout=3  nginx.netpolicy -O foo.html"
    cmd = await unit.run(query_from_good)
    assert cmd.status == 'completed'
    assert "foo.html" in cmd.data['results']['Stderr']
    cmd = await unit.run(query_from_bad)
    assert cmd.status == 'completed'
    assert "timed out" in cmd.data['results']['Stderr']

    # Clean-up namespace from next runs.
    cmd = await unit.run('/snap/bin/kubectl delete ns netpolicy')
    assert cmd.status == 'completed'


@log_calls_async
async def validate_worker_master_removal(model):
    # Add a second master
    masters = model.applications['kubernetes-master']
    unit_count = len(masters.units)
    if unit_count < 2:
        await masters.add_unit(1)
    await wait_for_ready(model)

    # Add a second worker
    workers = model.applications['kubernetes-worker']
    unit_count = len(workers.units)
    if unit_count < 2:
        await workers.add_unit(1)
    await wait_for_ready(model)
    unit_count = len(workers.units)

    # Remove a worker to see how the masters handle it
    await workers.units[0].remove()
    while len(workers.units) == unit_count:
        await asyncio.sleep(3)
        log('Waiting for worker removal.')
        assert_no_unit_errors(model)
    await wait_for_ready(model)

    # Remove the master leader
    unit_count = len(masters.units)
    for master in masters.units:
        if await master.is_leader_from_status():
            await master.remove()
    while len(masters.units) == unit_count:
        await asyncio.sleep(3)
        log('Waiting for master removal.')
        assert_no_unit_errors(model)
    await wait_for_ready(model)


@log_calls_async
async def validate_extra_args(model):
    async def get_service_args(app, service):
        results = []
        for unit in app.units:
            action = await unit.run('pgrep -af ' + service)
            assert action.status == 'completed'
            raw_output = action.data['results']['Stdout']
            arg_string = raw_output.partition(' ')[2].partition(' ')[2]
            args = {arg.strip() for arg in arg_string.split('--')[1:]}
            results.append(args)
        return results

    @log_calls_async
    async def run_extra_args_test(app_name, new_config, expected_args):
        app = model.applications[app_name]
        original_config = await app.get_config()
        original_args = {}
        for service in expected_args:
            original_args[service] = await get_service_args(app, service)

        await app.set_config(new_config)

        with timeout_for_current_task(600):
            for service, expected_service_args in expected_args.items():
                while True:
                    args_per_unit = await get_service_args(app, service)
                    if all(expected_service_args <= args for args in args_per_unit):
                        break
                    await asyncio.sleep(3)

        filtered_original_config = {
            key: original_config[key]['value']
            for key in new_config
        }
        await app.set_config(filtered_original_config)

        with timeout_for_current_task(600):
            for service, original_service_args in original_args.items():
                while True:
                    new_args = await get_service_args(app, service)
                    if new_args == original_service_args:
                        break
                    await asyncio.sleep(3)

    master_task = run_extra_args_test(
        app_name='kubernetes-master',
        new_config={
            'api-extra-args': ' '.join([
                'min-request-timeout=314',  # int arg, overrides a charm default
                'watch-cache',              # bool arg, implied true
                'enable-swagger-ui=false'   # bool arg, explicit false
            ]),
            'controller-manager-extra-args': ' '.join([
                'v=3',                        # int arg, overrides a charm default
                'profiling',                  # bool arg, implied true
                'contention-profiling=false'  # bool arg, explicit false
            ]),
            'scheduler-extra-args': ' '.join([
                'v=3',                        # int arg, overrides a charm default
                'profiling',                  # bool arg, implied true
                'contention-profiling=false'  # bool arg, explicit false
            ])
        },
        expected_args={
            'kube-apiserver': {
                'min-request-timeout 314',
                'watch-cache',
                'enable-swagger-ui=false'
            },
            'kube-controller-manager': {
                'v 3',
                'profiling',
                'contention-profiling=false'
            },
            'kube-scheduler': {
                'v 3',
                'profiling',
                'contention-profiling=false'
            }
        }
    )

    worker_task = run_extra_args_test(
        app_name='kubernetes-worker',
        new_config={
            'kubelet-extra-args': ' '.join([
                'v=1',                   # int arg, overrides a charm default
                'enable-server',         # bool arg, implied true
                'alsologtostderr=false'  # bool arg, explicit false
            ]),
            'proxy-extra-args': ' '.join([
                'v=1',                   # int arg, overrides a charm default
                'profiling',             # bool arg, implied true
                'alsologtostderr=false'  # bool arg, explicit false
            ])
        },
        expected_args={
            'kubelet': {
                'v 1',
                'enable-server',
                'alsologtostderr=false'
            },
            'kube-proxy': {
                'v 1',
                'profiling',
                'alsologtostderr=false'
            }
        }
    )

    await asyncio.gather(master_task, worker_task)


@log_calls_async
async def validate_sans(model):
    example_domain = "santest.example.com"
    app = model.applications['kubernetes-master']
    original_config = await app.get_config()
    lb = None
    original_lb_config = None
    if 'kubeapi-load-balancer' in model.applications:
        lb = model.applications['kubeapi-load-balancer']
        original_lb_config = await lb.get_config()

    async def get_server_certs():
        results = []
        for unit in app.units:
            action = await unit.run('openssl s_client -connect 127.0.0.1:6443 </dev/null 2>/dev/null | openssl x509 -text')
            assert action.status == 'completed'
            raw_output = action.data['results']['Stdout']
            results.append(raw_output)

        # if there is a load balancer, ask it as well
        if lb is not None:
            for unit in lb.units:
                action = await unit.run('openssl s_client -connect 127.0.0.1:443 </dev/null 2>/dev/null | openssl x509 -text')
                assert action.status == 'completed'
                raw_output = action.data['results']['Stdout']
                results.append(raw_output)

        return results

    # add san to extra san list
    await app.set_config({'extra_sans': example_domain})
    if lb is not None:
        await lb.set_config({'extra_sans': example_domain})

    # wait for server certs to update
    deadline = time.time() + 600
    while time.time() < deadline:
        certs = await get_server_certs()
        if all(example_domain in cert for cert in certs):
            break
        await asyncio.sleep(3)
    else:
        raise TimeoutError('extra sans config did not propogate to server certs')

    # now remove it
    await app.set_config({'extra_sans': ''})
    if lb is not None:
        await lb.set_config({'extra_sans': ''})

    # verify it went away
    deadline = time.time() + 600
    while time.time() < deadline:
        certs = await get_server_certs()
        if not any(example_domain in cert for cert in certs):
            break
        await asyncio.sleep(3)
    else:
        raise TimeoutError('extra sans config removal did not propogate to server certs')

    # reset back to what they had before
    await app.set_config({'extra_sans': original_config['extra_sans']['value']})
    if lb is not None and original_lb_config is not None:
        await lb.set_config({'extra_sans': original_lb_config['extra_sans']['value']})


@log_calls_async
async def validate_docker_logins(model):
    # Choose a worker. He shall be our vessel.
    app = model.applications['kubernetes-worker']
    vessel = app.units[0]

    async def run_until_success(cmd):
        while True:
            action = await vessel.run(cmd)
            assert action.status == 'completed'
            if action.data['results']['Code'] == '0':
                return action.data['results']['Stdout']
            else:
                log('Command failed on unit ' + vessel.entity_id)
                log('cmd: ' + cmd)
                log('code: ' + action.data['results']['Code'])
                log('stdout:\n' + action.data['results']['Stdout'].strip())
                log('stderr:\n' + action.data['results']['Stderr'].strip())
                log('Will retry...')
                await asyncio.sleep(1)

    async def kubectl(cmd):
        cmd = '/snap/bin/kubectl --kubeconfig /root/cdk/kubeconfig ' + cmd
        return await run_until_success(cmd)

    @log_calls_async
    async def wait_for_test_pod_state(desired_state, desired_reason=None):
        while True:
            data = await kubectl_get('po test-registry-user')
            status = data['status']
            if 'containerStatuses' in status:
                container_status = status['containerStatuses'][0]
                state, details = list(container_status['state'].items())[0]
                if desired_reason:
                    reason = details.get('reason')
                    if state == desired_state and reason == desired_reason:
                        break
                elif state == desired_state:
                    break
            await asyncio.sleep(1)

    @log_calls_async
    async def kubectl_delete(target):
        cmd = 'delete --ignore-not-found ' + target
        return await kubectl(cmd)

    @log_calls_async
    async def cleanup():
        await app.set_config({'docker-logins': '[]'})
        await kubectl_delete('po test-registry-user')
        await kubectl_delete('po test-registry')
        await kubectl_delete('svc test-registry')
        await kubectl_delete('secret test-registry')
        cmd = 'rm -rf /tmp/test-registry'
        await run_until_success(cmd)
        log('Waiting for pods to finish terminating...')
        while True:
            output = await kubectl('get po')
            if 'test-registry' not in output:
                break
            await asyncio.sleep(1)

    @log_calls_async
    async def kubectl_get(target):
        cmd = 'get -o json ' + target
        output = await kubectl(cmd)
        return json.loads(output)

    @log_calls_async
    async def kubectl_create(definition):
        with NamedTemporaryFile('w') as f:
            json.dump(definition, f)
            f.flush()
            await scp_to(f.name, vessel, '/tmp/test-registry/temp.yaml')
        await kubectl('create -f /tmp/test-registry/temp.yaml')

    # Start with a clean environment
    await cleanup()
    await run_until_success('mkdir -p /tmp/test-registry')
    await run_until_success('chown ubuntu:ubuntu /tmp/test-registry')

    # Create registry secret
    here = os.path.dirname(os.path.abspath(__file__))
    htpasswd = os.path.join(here, 'templates', 'test-registry', 'htpasswd')
    await scp_to(htpasswd, vessel, '/tmp/test-registry')
    cmd = 'openssl req -x509 -newkey rsa:4096 -keyout /tmp/test-registry/tls.key -out /tmp/test-registry/tls.crt -days 2 -nodes -subj /CN=localhost'
    await run_until_success(cmd)
    await kubectl('create secret generic test-registry'
        + ' --from-file=/tmp/test-registry/htpasswd'
        + ' --from-file=/tmp/test-registry/tls.crt'
        + ' --from-file=/tmp/test-registry/tls.key'
    )

    # Create registry
    await kubectl_create({
        'apiVersion': 'v1',
        'kind': 'Pod',
        'metadata': {
            'name': 'test-registry',
            'labels': {
                'app': 'test-registry'
            }
        },
        'spec': {
            'containers': [{
                'name': 'registry',
                'image': 'registry:2.6.2',
                'ports': [{
                    'containerPort': 5000,
                    'protocol': 'TCP'
                }],
                'env': [
                    {'name': 'REGISTRY_AUTH_HTPASSWD_REALM', 'value': 'test-registry'},
                    {'name': 'REGISTRY_AUTH_HTPASSWD_PATH', 'value': '/secret/htpasswd'},
                    {'name': 'REGISTRY_HTTP_TLS_KEY', 'value': '/secret/tls.key'},
                    {'name': 'REGISTRY_HTTP_TLS_CERTIFICATE', 'value': '/secret/tls.crt'}
                ],
                'volumeMounts': [
                    {
                        'name': 'secret',
                        'mountPath': '/secret'
                    },
                    {
                        'name': 'data',
                        'mountPath': '/var/lib/registry'
                    }
                ]
            }],
            'volumes': [
                {
                    'name': 'secret',
                    'secret': {
                        'secretName': 'test-registry'
                    }
                },
                {
                    'name': 'data',
                    'emptyDir': {}
                }
            ]
        }
    })
    await kubectl_create({
        'apiVersion': 'v1',
        'kind': 'Service',
        'metadata': {
            'name': 'test-registry'
        },
        'spec': {
            'type': 'NodePort',
            'selector': {
                'app': 'test-registry'
            },
            'ports': [{
                'protocol': 'TCP',
                'port': 5000,
                'targetPort': 5000
            }]
        }
    })
    registry_service = await kubectl_get('service test-registry')
    registry_port = registry_service['spec']['ports'][0]['nodePort']
    registry_url = 'localhost:%s' % registry_port

    # Upload test container
    cmd = 'docker login %s -u test-user -p yyDVinHE' % registry_url
    await run_until_success(cmd)
    cmd = 'docker pull ubuntu:16.04'
    await run_until_success(cmd)
    cmd = 'docker tag ubuntu:16.04 %s/ubuntu:16.04' % registry_url
    await run_until_success(cmd)
    cmd = 'docker push %s/ubuntu:16.04' % registry_url
    await run_until_success(cmd)
    cmd = 'docker rmi %s/ubuntu:16.04' % registry_url
    await run_until_success(cmd)
    cmd = 'docker logout %s' % registry_url
    await run_until_success(cmd)

    # Create test pod using our registry
    await kubectl_create({
        'apiVersion': 'v1',
        'kind': 'Pod',
        'metadata': {
            'name': 'test-registry-user'
        },
        'spec': {
            'containers': [{
                'name': 'ubuntu',
                'image': registry_url + '/ubuntu:16.04',
                'command': ['sleep', '3600']
            }]
        }
    })

    # Verify pod fails image pull
    await wait_for_test_pod_state('waiting', 'ImagePullBackOff')

    # Configure docker_logins
    docker_logins = [{'server': registry_url, 'username': 'test-user', 'password': 'yyDVinHE'}]
    await app.set_config({'docker-logins': json.dumps(docker_logins)})

    # Verify pod enters running state
    await wait_for_test_pod_state('running')

    # Restore config and clean up
    await cleanup()


class MicrobotError(Exception):
    pass
