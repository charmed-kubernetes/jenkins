import asyncio
import os
import requests
import time
import traceback
import yaml

from tempfile import NamedTemporaryFile

from utils import assert_no_unit_errors, asyncify, wait_for_ready


async def validate_all(model, log_dir):
    validate_status_messages(model)
    await validate_snap_versions(model)
    await validate_microbot(model)
    await validate_dashboard(model, log_dir)
    await validate_kubelet_anonymous_auth_disabled(model)
    await validate_e2e_tests(model, log_dir)
    await validate_worker_removal(model)
    await validate_sans(model)
    if "canal" in model.applications:
        print("Running canal specific tests")
        await validate_network_policies(model)
    await validate_api_extra_args(model)
    assert_no_unit_errors(model)


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
            print(message)
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


async def validate_microbot(model):
    ''' Validate the microbot action '''
    unit = model.applications['kubernetes-worker'].units[0]
    action = await unit.run_action('microbot', replicas=3)
    await action.wait()
    assert action.status == 'completed'
    for i in range(60):
        try:
            resp = await asyncify(requests.get)('http://' + action.data['results']['address'])
            if resp.status_code == 200:
                return
        except requests.exceptions.ConnectionError:
            print("Caught connection error attempting to hit xip.io, retrying. Error follows:")
            traceback.print_exc()
        await asyncio.sleep(1)
    raise MicrobotError('Microbot failed to start.')


async def validate_dashboard(model, log_dir):
    ''' Validate that the dashboard is operational '''
    unit = model.applications['kubernetes-master'].units[0]
    with NamedTemporaryFile() as f:
        await unit.scp_from('config', f.name)
        with open(f.name, 'r') as stream:
            config = yaml.load(stream)
    url = config['clusters'][0]['cluster']['server']
    user = config['users'][0]['user']['username']
    password = config['users'][0]['user']['password']
    auth = requests.auth.HTTPBasicAuth(user, password)
    resp = await asyncify(requests.get)(url, auth=auth, verify=False)
    assert resp.status_code == 200
    url = '%s/api/v1/namespaces/kube-system/services/kubernetes-dashboard/proxy/api/v1/workload/default?filterBy=&itemsPerPage=10&page=1&sortBy=d,creationTimestamp'
    url %= config['clusters'][0]['cluster']['server']
    resp = await asyncify(requests.get)(url, auth=auth, verify=False)
    assert resp.status_code == 200
    data = resp.json()
    with open(os.path.join(log_dir, 'dashboard.yaml'), 'w') as f:
        yaml.dump(data, f, default_flow_style=False)


async def validate_kubelet_anonymous_auth_disabled(model):
    ''' Validate that kubelet has anonymous auth disabled '''
    async def validate_unit(unit):
        await unit.run('open-port 10250')
        address = unit.public_address
        url = 'https://%s:10250/pods/' % address
        response = await asyncify(requests.get)(url, verify=False)
        assert response.status_code == 401  # Unauthorized
    units = model.applications['kubernetes-worker'].units
    await asyncio.gather(*(validate_unit(unit) for unit in units))


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
        action = await e2e_unit.run_action('test')
        await action.wait()
        for suffix in ['.log', '-junit.tar.gz']:
            src = action.entity_id + suffix
            dest = os.path.join(log_dir, 'e2e-%d' % attempts + suffix)
            await e2e_unit.scp_from(src, dest)
        if action.status == 'completed':
            break
        else:
            print("Attempt %d/3 failed." % attempts)

    assert action.status == 'completed'


async def validate_network_policies(model):
    ''' Apply network policy and use two busyboxes to validate it. '''
    here = os.path.dirname(os.path.abspath(__file__))
    unit = model.applications['kubernetes-master'].units[0]

    # Clean-up namespace from any previous runs.
    cmd = await unit.run('/snap/bin/kubectl delete ns netpolicy')
    assert cmd.status == 'completed'

    # Move menaifests to the master
    await unit.scp_to(os.path.join(here, "templates", "netpolicy-test.yaml"), "netpolicy-test.yaml")
    await unit.scp_to(os.path.join(here, "templates", "restrict.yaml"), "restrict.yaml")
    cmd = await unit.run('/snap/bin/kubectl create -f /home/ubuntu/netpolicy-test.yaml')
    assert cmd.status == 'completed'
    await asyncio.sleep(10)

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


async def validate_worker_removal(model):
    workers = model.applications['kubernetes-worker']
    unit_count = len(workers.units)
    if unit_count < 2:
        await workers.add_unit(1)
    await wait_for_ready(model)
    unit_count = len(workers.units)
    await workers.units[0].remove()
    while len(workers.units) == unit_count:
        await asyncio.sleep(1)
        print('Waiting for worker removal.')
        assert_no_unit_errors(model)
    await wait_for_ready(model)


async def validate_api_extra_args(model):
    app = model.applications['kubernetes-master']
    original_config = await app.get_config()

    async def get_apiserver_args():
        results = []
        for unit in app.units:
            action = await unit.run('pgrep -a kube-apiserver')
            assert action.status == 'completed'
            raw_output = action.data['results']['Stdout']
            arg_string = raw_output.partition(' ')[2].partition(' ')[2]
            args = {arg.strip() for arg in arg_string.split('--')[1:]}
            results.append(args)
        return results

    original_args = await get_apiserver_args()

    extra_args = ' '.join([
        'min-request-timeout=314',  # int arg, overrides a charm default
        'watch-cache',              # bool arg, implied true
        'enable-swagger-ui=false'   # bool arg, explicit false
    ])
    await app.set_config({'api-extra-args': extra_args})

    expected_args = {
        'min-request-timeout 314',
        'watch-cache',
        'enable-swagger-ui=false'
    }

    deadline = time.time() + 60
    while time.time() < deadline:
        args_per_unit = await get_apiserver_args()
        if all(expected_args <= args for args in args_per_unit):
            break
        await asyncio.sleep(1)
    else:
        raise TimeoutError('api-extra-args config did not propagate')

    original_args_config = original_config['api-extra-args']['value']
    await app.set_config({'api-extra-args': original_args_config})

    deadline = time.time() + 60
    while time.time() < deadline:
        new_args = await get_apiserver_args()
        if new_args == original_args:
            break
        await asyncio.sleep(1)
    else:
        raise TimeoutError('api-extra-args config did not restore properly')


async def validate_sans(model):
    example_domain = "santest.example.com"
    app = model.applications['kubernetes-master']
    original_config = await app.get_config()
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
        if lb:
            for unit in lb.units:
                action = await unit.run('openssl s_client -connect 127.0.0.1:443 </dev/null 2>/dev/null | openssl x509 -text')
                assert action.status == 'completed'
                raw_output = action.data['results']['Stdout']
                results.append(raw_output)

        return results

    # add san to extra san list
    await app.set_config({'extra_sans': example_domain})
    if lb:
        await lb.set_config({'extra_sans': example_domain})

    # wait for server certs to update
    deadline = time.time() + 60
    while time.time() < deadline:
        certs = await get_server_certs()
        if all(example_domain in cert for cert in certs):
            break
        await asyncio.sleep(1)
    else:
        raise TimeoutError('extra sans config did not propogate to server certs')

    # now remove it
    await app.set_config({'extra_sans': ''})
    if lb:
        await lb.set_config({'extra_sans': ''})

    # verify it went away
    deadline = time.time() + 60
    while time.time() < deadline:
        certs = await get_server_certs()
        if not any(example_domain in cert for cert in certs):
            break
        await asyncio.sleep(1)
    else:
        raise TimeoutError('extra sans config removal did not propogate to server certs')

    # reset back to what they had before
    await app.set_config({'extra_sans': original_config['extra_sans']['value']})
    if lb and original_lb_config:
        await lb.set_config({'extra_sans': original_lb_config['extra_sans']['value']})


class MicrobotError(Exception):
    pass
