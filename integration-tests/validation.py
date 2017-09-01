import asyncio
import os
import requests
import traceback
import yaml
import kubernetes

from tempfile import NamedTemporaryFile

from utils import assert_no_unit_errors, asyncify, wait_for_ready


async def validate_all(model, log_dir):
    validate_status_messages(model)
    await validate_snap_versions(model)
    await validate_microbot(model)
    await validate_dashboard(model, log_dir)
    await validate_kubelet_anonymous_auth_disabled(model)
    await validate_e2e_tests(model, log_dir)
    if "canal" in model.applications:
        print("Running canal specific tests")
        await validate_network_policies(model)
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
    ''' Apply network policy and test it '''
    here = os.path.dirname(os.path.abspath(__file__))
    policy_test_ns = "netpolicy"
    unit = model.applications['kubernetes-master'].units[0]
    with NamedTemporaryFile() as f:
        await unit.scp_from('config', f.name)
        config = kubernetes.config.load_kube_config(f.name)

    core = kubernetes.client.CoreV1Api()
    # Clean namespace before testing
    namespaces = core.list_namespace()
    for ns in namespaces.items:
        if ns.metadata.name == policy_test_ns:
            opts = kubernetes.client.V1DeleteOptions()
            core.delete_namespace(policy_test_ns, opts)
            # Kubernetes takes some time to remove services stop pods etc.
            await asyncio.sleep(60)

    # Create the namespace
    with open(os.path.join(here, "templates", "network-namespace.yaml")) as f:
        ns_body = yaml.load(f)
        core.create_namespace(ns_body)

    # Create the deployment
    with open(os.path.join(here, "templates", "nginx-deployment.yaml")) as f:
        dep = yaml.load(f)
        k8s_beta = kubernetes.client.ExtensionsV1beta1Api()
        resp = k8s_beta.create_namespaced_deployment(
            body=dep, namespace=policy_test_ns)

    # Create the service
    with open(os.path.join(here, "templates", "nginx-service.yaml")) as f:
        svc = yaml.load(f)
        core.create_namespaced_service(namespace=policy_test_ns, body=svc)

    # Get to nginx
    resp = await exec_in_pod(core, "wget nginx.{}".format(policy_test_ns),
                             namespace = policy_test_ns)
    assert "index.html" in resp

    # Restrict access
    with open(os.path.join(here, "templates", "restrict.yaml")) as f:
        np = yaml.load(f)
        net_api = kubernetes.client.NetworkingV1Api()
        net_api.create_namespaced_network_policy(policy_test_ns, np)

    # Fail to get to nginx
    resp = await exec_in_pod(core, "wget --timeout=3 nginx.{}".format(policy_test_ns),
                             label='retry', namespace=policy_test_ns)
    assert "index.html" not in resp


async def exec_in_pod(api, command, label='nolabel', namespace="netpolicy"):
    ''' Create a busybox and run a command. '''
    name = 'busybox-{}-netpolicy'.format(label)
    print("Creating pod...{}".format(name))
    pod_manifest = {
        'apiVersion': 'v1',
        'kind': 'Pod',
        'metadata': {
            'name': name,
        },
        'spec': {
            'containers': [{
                'image': 'busybox',
                'name': 'sleep',
                "args": [
                    "/bin/sh",
                    "-c",
                    "while true;do date;sleep 5; done"
                ]
            }]
        }
    }
    api.create_namespaced_pod(body=pod_manifest,
                                     namespace=namespace)
    while True:
        resp = api.read_namespaced_pod(name=name,
                                       namespace=namespace)
        if resp.status.phase != 'Pending':
            break
        asyncio.sleep(10)
    print("Done creating {}.".format(namespace))

    # calling exec and wait for response.
    exec_command = [
        '/bin/sh',
        '-c',
        command]
    resp = api.connect_get_namespaced_pod_exec(name, namespace,
                                               command=exec_command,
                                               stderr=True, stdin=False,
                                               stdout=True, tty=False)
    print("Response: " + resp)
    return resp


class MicrobotError(Exception):
    pass
