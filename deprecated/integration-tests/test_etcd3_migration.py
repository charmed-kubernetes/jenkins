import os
import pytest
from subprocess import check_call
from tempfile import TemporaryDirectory
from utils import temporary_model, upgrade_charms, deploy_e2e
from utils import juju_deploy, default_bundles, asyncify
from validation import validate_all

check_call = asyncify(check_call)

namespace = os.environ.get('TEST_CHARM_NAMESPACE', 'containers')
charm_channel = os.environ.get('TEST_CHARM_CHANNEL', 'stable')
snap_channel = os.environ.get('TEST_SNAP_CHANNEL', '1.9/stable')
test_cloud = os.environ.get('TEST_CLOUD', '')
bundles_csv = os.environ.get('TEST_BUNDLES', default_bundles())
bundles = [bundle.strip() for bundle in bundles_csv.split(',')]


@pytest.mark.asyncio
@pytest.mark.parametrize('bundle', bundles)
async def test_upgrade_migration(bundle, log_dir):
    async with temporary_model(log_dir, force_cloud=test_cloud) as model:
        await juju_deploy(model, namespace, bundle, 'stable')
        await upgrade_charms(model, charm_channel)

        with TemporaryDirectory() as tmpdirname:
            cmd = 'git clone https://github.com/juju-solutions/cdk-cli.git %s' % tmpdirname
            await check_call(cmd, shell=True)
            cmd = '%s/scripts/cdk migrate etcd 2to3' % tmpdirname
            await check_call(cmd, shell=True)

        await deploy_e2e(model, charm_channel, snap_channel, namespace=namespace)
        await validate_all(model, log_dir)
