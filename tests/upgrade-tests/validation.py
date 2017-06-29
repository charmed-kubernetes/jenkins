import asyncio
import requests
from utils import assert_no_unit_errors, asyncify


async def validate_all(model):
    validate_status_messages(model)
    await validate_snap_versions(model)
    await validate_microbot(model)
    await validate_kubelet_anonymous_auth_disabled(model)
    await validate_e2e_tests(model)
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
    # TODO: wait for pods running
    # TODO: test that we can reach the ingress endpoint


async def validate_kubelet_anonymous_auth_disabled(model):
    ''' Validate that kubelet has anonymous auth disabled '''
    async def validate_unit(unit):
        await unit.run('open-port 10250')
        address = unit.public_address
        url = 'https://%s:10250/runningpods/' % address
        response = await asyncify(requests.get)(url, verify=False)
        assert response.status_code == 401  # Unauthorized
    units = model.applications['kubernetes-worker'].units
    await asyncio.gather(*(validate_unit(unit) for unit in units))


async def validate_e2e_tests(model):
    ''' Validate that the e2e tests pass.'''
    e2e_unit = model.applications['kubernetes-e2e'].units[0]
    action = await e2e_unit.run_action('test')
    await action.wait()
    assert action.status == 'completed'
