""" EasyRSA charm testing
"""
import pytest
import os
import json
from pathlib import Path
from ..base import _juju_wait
from ..utils import asyncify
from sh import curl, juju

pytestmark = pytest.mark.asyncio

# Locally built charm layer path
CHARM_PATH = os.getenv("CHARM_PATH")

relation_data = None


async def easyrsa_resource():
    URL = (
        "https://github.com/OpenVPN/easy-rsa/releases/download/"
        "3.0.1/EasyRSA-3.0.1.tgz"
    )
    if not Path("/tmp/easyrsa.tgz").exists():
        await asyncify(curl)("-L", "-k", "-o", "/tmp/easyrsa.tgz", URL)
    return "/tmp/easyrsa.tgz"


async def deploy_easyrsa(controller, model):
    resource_path = await easyrsa_resource()
    await asyncify(juju)(
        "deploy",
        "-m",
        "{}:{}".format(controller, model),
        str(CHARM_PATH),
        "--resource",
        "easyrsa={}".format(resource_path),
    )
    await asyncify(_juju_wait)(controller, model)


async def deploy_test_app(controller, model):
    test_app = "etcd"

    await asyncify(juju)("deploy", "-m", "{}:{}".format(controller, model), test_app)
    await asyncify(juju)(
        "relate", "-m", "{}:{}".format(controller, model), test_app, "easyrsa"
    )
    await asyncify(_juju_wait)(controller, model)


async def get_relation_data(controller, model):
    """Gets data from the relation specified"""
    global relation_data

    if relation_data is None:
        await deploy_easyrsa(controller, model.info.name)
        await deploy_test_app(controller, model.info.name)
        easyrsa = model.applications["easyrsa"]
        easyrsa = easyrsa.units[0]

        id = await easyrsa.run("relation-ids client")  # magic :(
        id = id.results["Stdout"].strip()
        raw_json = await easyrsa.run(
            "relation-get --format=json -r {} - {}".format(id, easyrsa.name)
        )
        relation_data = json.loads(raw_json.results["Stdout"])
    return relation_data


async def test_easyrsa_installed(deploy, event_loop):
    """Test that EasyRSA software is installed."""
    controller, model = deploy
    await deploy_easyrsa(controller, model.info.name)
    easyrsa = model.applications["easyrsa"]
    easyrsa = easyrsa.units[0]
    charm_dir = Path("/var/lib/juju/agents/{tag}/charm".format(tag=easyrsa.tag))
    easyrsa_dir = charm_dir / "EasyRSA"
    # Create a path to the easyrsa schell script.
    easyrsa_path = easyrsa_dir / "easyrsa"
    output = await asyncify(juju)(
        "ssh",
        "-m",
        "{}:{}".format(controller, model.info.name),
        easyrsa.name,
        "cat {}".format(str(easyrsa_path)),
    )
    output = output.stdout.decode().strip()
    assert output != ""
    assert "Easy-RSA" in output


async def test_ca(deploy, event_loop):
    controller, model = deploy
    await deploy_easyrsa(controller, model.info.name)
    easyrsa = model.applications["easyrsa"]
    easyrsa = easyrsa.units[0]
    """Test that the ca and key were created."""
    charm_dir = Path("/var/lib/juju/agents/{tag}/charm".format(tag=easyrsa.tag))
    easyrsa_dir = os.path.join(charm_dir, "EasyRSA")
    # Create an absolute path to the ca.crt file.
    ca_path = os.path.join(easyrsa_dir, "pki/ca.crt")
    # Get the CA certificiate.
    ca_cert = await asyncify(juju)(
        "ssh",
        "-m",
        "{}:{}".format(controller, model.info.name),
        easyrsa.name,
        "sudo cat {}".format(str(ca_path)),
    )
    ca_cert = ca_cert.stdout.decode().strip()
    assert validate_certificate(ca_cert)
    # Create an absolute path to the ca.key
    key_path = os.path.join(easyrsa_dir, "pki/private/ca.key")
    # Get the CA key.
    ca_key = await asyncify(juju)(
        "ssh",
        "-m",
        "{}:{}".format(controller, model.info.name),
        easyrsa.name,
        "sudo cat {}".format(str(key_path)),
    )
    ca_key = ca_key.stdout.decode().strip()
    assert validate_key(ca_key)
    # Create an absolute path to the installed location of the ca.
    ca_crt_path = "/usr/local/share/ca-certificates/{service}.crt".format(
        service=easyrsa.name.split("/")[0]
    )
    installed_ca = await asyncify(juju)(
        "ssh",
        "-m",
        "{}:{}".format(controller, model.info.name),
        easyrsa.name,
        "sudo cat {}".format(str(ca_crt_path)),
    )
    installed_ca = installed_ca.stdout.decode().strip()
    assert validate_certificate(installed_ca)
    assert ca_cert == installed_ca


async def test_client(deploy, event_loop):
    """Test that the client certificate and key can be created."""
    controller, model = deploy
    relation_data = await get_relation_data(controller, model)
    assert validate_certificate(relation_data["client.cert"])
    assert validate_key(relation_data["client.key"])


async def test_server(deploy, event_loop):
    """Test that the server certificate and key can be created."""
    controller, model = deploy
    relation_data = await get_relation_data(controller, model)
    # find server certs and keys
    server_certs = {
        key: data for key, data in relation_data.items() if ".server.cert" in key
    }
    server_keys = {
        key: data for key, data in relation_data.items() if ".server.key" in key
    }

    for _, cert in server_certs.items():
        assert validate_certificate(cert)
    for _, key in server_keys.items():
        assert validate_key(key)


def validate_certificate(cert):
    """Return true if the certificate is valid, false otherwise."""
    # The cert should not be empty and have begin and end statesments.
    return cert and "BEGIN CERTIFICATE" in cert and "END CERTIFICATE" in cert


def validate_key(key):
    """Return true if the key is valid, false otherwise."""
    # The key should not be empty string and have begin and end statements.
    return key and "BEGIN PRIVATE KEY" in key and "END PRIVATE KEY" in key
