""" EasyRSA charm testing
"""
import pytest
import os
from pathlib import Path
from ..base import _juju_wait

pytestmark = pytest.mark.asyncio

# Locally built charm layer path
CHARM_PATH = os.getenv('CHARM_PATH')


@pytest.mark.skip('Need local resources work')
async def test_local_deployed(deploy, event_loop):
    """ Verify local easy charm can be deployed """
    controller, model = deploy
    await model.deploy(str(CHARM_PATH))
    _juju_wait(controller, model.info.name)
    assert 'easyrsa' in model.applications


@pytest.mark.skip('Need local resources work')
async def test_easyrsa_installed(deploy, event_loop):
    '''Test that EasyRSA software is installed.'''
    controller, model = deploy
    easyrsa = await model.deploy(str(CHARM_PATH))
    easyrsa = easyrsa.units[0]
    charm_dir = Path('/var/lib/juju/agents/unit-{service}-{unit}/charm'.format(
        service=easyrsa.name, unit=easyrsa.id))
    easyrsa_dir = charm_dir / 'EasyRSA'
    # Create a path to the easyrsa schell script.
    easyrsa_path = easyrsa_dir / 'easyrsa'
    # Get the contents of the easyrsa shell script.
    easyrsa_fc = await easyrsa.scp_from(str(easyrsa_path), '.')
    output = easyrsa_fc.read_text()
    assert output != ''
    assert 'Easy-RSA' in output


@pytest.mark.skip('Need local resources work')
async def test_ca(deploy, event_loop):
    controller, model = deploy
    easyrsa = await model.deploy(str(CHARM_PATH))
    easyrsa = easyrsa.units[0]
    '''Test that the ca and key were created.'''
    charm_dir = '/var/lib/juju/agents/unit-{service}-{unit}/charm'.format(
        service=easyrsa.name, unit=easyrsa.id)
    easyrsa_dir = os.path.join(charm_dir, 'EasyRSA')
    # Create an absolute path to the ca.crt file.
    ca_path = os.path.join(easyrsa_dir, 'pki/ca.crt')
    # Get the CA certificiate.
    ca_cert = easyrsa.scp_from(ca_path, Path('.'))
    assert validate_certificate(ca_cert)
    # Create an absolute path to the ca.key
    key_path = os.path.join(easyrsa_dir, 'pki/private/ca.key')
    # Get the CA key.
    ca_key = easyrsa.scp_from(key_path, Path('.'))
    assert validate_key(ca_key)
    # Create an absolute path to the installed location of the ca.
    ca_crt_path = '/usr/local/share/ca-certificates/{service}.crt'.format(
        service=easyrsa.name)
    installed_ca = easyrsa.scp_from(ca_crt_path, Path('.'))
    assert validate_certificate(installed_ca)
    assert ca_cert == installed_ca


@pytest.mark.skip('Need local resources work')
async def test_client(deploy, event_loop):
    '''Test that the client certificate and key were created.'''
    controller, model = deploy
    easyrsa = await model.deploy(str(CHARM_PATH))
    easyrsa = easyrsa.units[0]

    charm_dir = '/var/lib/juju/agents/unit-{service}-{unit}/charm'.format(
        service=easyrsa.name, unit=easyrsa.id)
    easyrsa_dir = os.path.join(charm_dir, 'EasyRSA')
    # Create an absolute path to the client certificate.
    cert_path = os.path.join(easyrsa_dir, 'pki/issued/client.crt')
    client_cert = easyrsa.scp_from(cert_path, Path('.'))
    assert validate_certificate(client_cert)
    key_path = os.path.join(easyrsa_dir, 'pki/private/client.key')
    client_key = easyrsa.scp_from(key_path, Path('.'))
    assert validate_key(client_key)


def validate_certificate(cert):
    '''Return true if the certificate is valid, false otherwise.'''
    # The cert should not be empty and have begin and end statesments.
    return cert and 'BEGIN CERTIFICATE' in cert and 'END CERTIFICATE' in cert


def validate_key(key):
    '''Return true if the key is valid, false otherwise.'''
    # The key should not be empty string and have begin and end statements.
    return key and 'BEGIN PRIVATE KEY'in key and 'END PRIVATE KEY' in key
