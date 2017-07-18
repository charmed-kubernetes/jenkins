import os
import pytest
import subprocess
import yaml
from utils import temporary_model, conjureup, deploy_e2e, upgrade_charms
from utils import asyncify, juju_deploy
from validation import validate_all

namespace = os.environ.get('TEST_CHARMS_NAMESPACE', 'containers')
channel = os.environ.get('TEST_CHARMS_CHANNEL', 'edge')
bundles = [
    'kubernetes-core',
    #'canonical-kubernetes',
]


@pytest.mark.asyncio
@pytest.mark.parametrize('bundle', bundles)
async def test_deploy(bundle, log_dir):
    async with temporary_model(log_dir) as model:
        # await conjureup(model, namespace, bundle, channel)
        await juju_deploy(model, namespace, bundle, channel)
        await deploy_e2e(model, channel)
        await validate_all(model)


@pytest.mark.asyncio
@pytest.mark.parametrize('bundle', bundles)
async def test_upgrade(bundle, log_dir):
    async with temporary_model(log_dir) as model:
        # await conjureup(model, namespace, bundle, 'stable')
        await juju_deploy(model, namespace, bundle, channel)
        await upgrade_charms(model, channel)
        await deploy_e2e(model, channel)
        await validate_all(model)


@pytest.mark.asyncio
async def test_bundletester(log_dir):
    async with temporary_model(log_dir) as model:
        # fetch bundle
        bundle = 'canonical-kubernetes'
        url = 'cs:~%s/%s' % (namespace, bundle)
        bundle_dir = os.path.join(log_dir, bundle)
        cmd = ['charm', 'pull', url, '--channel', channel, bundle_dir]
        await asyncify(subprocess.check_call)(cmd)

        # update bundle config with label
        data_path = os.path.join(bundle_dir, 'bundle.yaml')
        with open(data_path, 'r') as f:
            data = yaml.load(f)
        data['services']['kubernetes-worker'].setdefault('options', {})['labels'] = 'mylabel=thebest'
        yaml.Dumper.ignore_aliases = lambda *args: True
        with open(data_path, 'w') as f:
            yaml.dump(data, f, default_flow_style=False)

        # run bundletester
        output_file = os.path.join(log_dir, 'bundletester.xml')
        cmd = [
            'bundletester',
            '--no-matrix', '-vF', '-l', 'DEBUG',
            '-t', bundle_dir,
            '-r', 'xml', '-o', output_file
        ]
        await asyncify(subprocess.check_call)(cmd)
