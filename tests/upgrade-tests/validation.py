from utils import assert_no_unit_errors


async def validate_all(model):
    validate_status_messages(model)
    await validate_microbot(model)
    assert_no_unit_errors(model)


def validate_status_messages(model):
    ''' Validate that the status messages are correct. '''
    expected_messages = {
        'kubernetes-master': 'Kubernetes master running.',
        'kubernetes-worker': 'Kubernetes worker running.'
    }
    for app, message in expected_messages.items():
        for unit in model.applications[app].units:
            assert unit.data['workload-status']['message'] == message


async def validate_microbot(model):
    ''' Validate the microbot action '''
    unit = model.applications['kubernetes-worker'].units[0]
    action = await unit.run_action('microbot', replicas=3)
    await action.wait()
    assert action.status == 'completed'
    # TODO: wait for pods running
    # TODO: test that we can reach the ingress endpoint
