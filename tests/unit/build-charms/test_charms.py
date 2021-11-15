import sys

sys.path.append("jobs/build-charms")

import os
from pathlib import Path

import pytest
from unittest.mock import patch

from click.testing import CliRunner
import charms

STATIC_TEST_PATH = Path(__file__).parent / "test_charms"


def test_build_env_missing_env():
    with pytest.raises(charms.BuildException) as ie:
        charms.BuildEnv()
    assert "build environment variables" in str(ie.value)


@pytest.fixture()
def test_environment():
    test_path = "/tmp"
    saved_env, test_env = {}, dict(
        CHARM_BUILD_DIR=test_path,
        CHARM_LAYERS_DIR=test_path,
        CHARM_INTERFACES_DIR=test_path,
        CHARM_CHARMS_DIR=test_path,
        WORKSPACE=test_path,
    )

    for k, v in test_env.items():
        saved_env[k], os.environ[k] = os.environ.get(k, None), v

    yield

    for k, v in saved_env.items():
        if v is None:
            del os.environ[k]
        else:
            os.environ[v] = saved_env[k]


@pytest.fixture()
def cilib_store():
    with patch("charms.Store") as store:
        yield store


@pytest.fixture()
def charm_cmd():
    with patch("charms.sh.charm") as cmd:
        cmd.show.return_value.stdout = b"""
            id:
              Id: cs:~containers/calico-845
              Name: calico
              Revision: 845
              User: containers
        """
        cmd.return_value.stdout = (
            STATIC_TEST_PATH / "charm_list-resources_cs_containers_calico-845.yaml"
        ).read_bytes()
        yield cmd


@pytest.fixture()
def charmcraft_cmd():
    with patch('charms.sh.charmcraft') as cmd:
        cmd.status.return_value.stdout = (
            STATIC_TEST_PATH / "charmcraft_status_containers-calico.txt"
        ).read_bytes()
        yield cmd


def test_build_env_promote_all_charmstore(test_environment, cilib_store, charm_cmd):
    charm_env = charms.BuildEnv(build_type=charms.BuildType.CHARM)
    charm_env.db["build_args"] = {
        "artifact_list": Path(__file__).parent / "test_charms" / "artifacts.yaml",
        "filter_by_tag": ["k8s"],
        "to_channel": "edge",
        "from_channel": "unpublished",
    }
    charm_env.promote_all()
    charm_entity = "cs:~containers/calico"
    charm_entity_ver = f"{charm_entity}-845"
    charm_cmd.show.assert_called_once_with(
        charm_entity, "--channel", "unpublished", "id"
    )
    charm_cmd.assert_called_once_with(
        "list-resources", charm_entity_ver, channel="unpublished", format="yaml"
    )
    resource_args = [
        ("--resource", "calico-995"),
        ("--resource", "calico-arm64-994"),
        ("--resource", "calico-node-image-677"),
        ("--resource", "calico-upgrade-822"),
        ("--resource", "calico-upgrade-arm64-822"),
    ]
    charm_cmd.release.assert_called_once_with(
        charm_entity_ver, "--channel", "edge", *resource_args
    )


def test_build_env_promote_all_charmhub(test_environment, cilib_store, charmcraft_cmd):
    charm_env = charms.BuildEnv(build_type=charms.BuildType.CHARM)
    charm_env.db["build_args"] = {
        "artifact_list": Path(__file__).parent / "test_charms" / "artifacts.yaml",
        "filter_by_tag": ["k8s"],
        "to_channel": "beta",
        "from_channel": "edge",
    }
    charm_env.promote_all(from_channel="edge", to_channel="beta", store="ch")
    resource_args = [
        "--resource=calico:994",
        "--resource=calico-arm64:993",
        "--resource=calico-node-image:676",
        "--resource=calico-upgrade:821",
        "--resource=calico-upgrade-arm64:821",
    ]
    charmcraft_cmd.release.assert_called_once_with(
        'containers-calico', "--revision=845", "--channel=beta", *resource_args
    )


@pytest.fixture()
def mock_build_env():
    with patch("charms.BuildEnv") as mock_env:
        mock_env_inst = mock_env.return_value
        mock_env_inst.db = {}
        yield mock_env_inst


def test_promote_command(mock_build_env):
    runner = CliRunner()
    result = runner.invoke(
        charms.promote,
        [
            "--charm-list",
            "test-charm",
            "--filter-by-tag",
            "tag1",
            "--filter-by-tag",
            "tag2",
            "--from-channel",
            "unpublished",
            "--to-channel",
            "edge",
        ],
    )
    assert result.exit_code == 0
    assert mock_build_env.db["build_args"] == {
        "artifact_list": "test-charm",
        "filter_by_tag": ["tag1", "tag2"],
        "to_channel": "edge",
        "from_channel": "unpublished",
    }
    mock_build_env.promote_all.assert_called_once_with(
        from_channel="unpublished", to_channel="edge"
    )
