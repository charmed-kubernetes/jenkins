"""Tests to verify jobs/build-charms/charms."""

import os
from pathlib import Path

import pytest
from unittest.mock import patch, call, PropertyMock

import yaml
from click.testing import CliRunner
import charms

STATIC_TEST_PATH = Path(__file__).parent / "test_charms"


def test_build_env_missing_env():
    """Ensure missing environment variables raise Exception."""
    with pytest.raises(charms.BuildException) as ie:
        charms.BuildEnv()
    assert "build environment variables" in str(ie.value)


@pytest.fixture()
def test_environment(tmpdir):
    """Creates a fixture defining test environment variables."""
    saved_env, test_env = {}, dict(
        CHARM_BUILD_DIR=f'{tmpdir / "build"}',
        CHARM_LAYERS_DIR=f'{tmpdir / "layers"}',
        CHARM_INTERFACES_DIR=f'{tmpdir / "interfaces"}',
        CHARM_CHARMS_DIR=f'{tmpdir / "charms"}',
        WORKSPACE=f'{tmpdir / "scratch"}',
    )

    for k, v in test_env.items():
        saved_env[k], os.environ[k] = os.environ.get(k, None), v

    yield

    for k, v in saved_env.items():
        if v is None:
            del os.environ[k]
        else:
            os.environ[v] = saved_env[k]


@pytest.fixture(autouse=True)
def cilib_store():
    """Create a fixture defining mock for cilib Store."""
    with patch("charms.Store") as store:
        yield store


@pytest.fixture(autouse=True)
def charm_cmd():
    """Create a fixture defining mock for `charm` cli command."""
    with patch("sh.charm", create=True) as cmd:
        cmd.show.return_value.stdout = b"""
id:
  Id: cs:~containers/calico-845
  Name: calico
  Revision: 845
  User: containers
extra-info:
  commit: 96b4e06d5d35fec30cdf2cc25076dd25c51b893c
        """
        cmd.return_value.stdout = (
            STATIC_TEST_PATH / "charm_list-resources_cs_containers_calico-845.yaml"
        ).read_bytes()
        yield cmd


@pytest.fixture(autouse=True)
def charmcraft_cmd():
    """Create a fixture defining mock for `charmcraft` cli command."""
    with patch("sh.charmcraft", create=True) as cmd:
        cmd.status.return_value.stdout = (
            STATIC_TEST_PATH / "charmcraft_status_containers-calico.txt"
        ).read_bytes()
        yield cmd


def test_build_env_promote_all_charmstore(test_environment, cilib_store, charm_cmd):
    """Test promote_all to the charmstore."""
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


def test_build_env_promote_all_charmhub(test_environment, charmcraft_cmd):
    """Tests promote_all to charmhub."""
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
        "calico", "--revision=845", "--channel=beta", *resource_args
    )


def test_build_entity_setup(test_environment):
    """Tests build entity setup."""
    charm_env = charms.BuildEnv(build_type=charms.BuildType.CHARM)
    charm_env.db["build_args"] = {
        "artifact_list": Path(__file__).parent / "test_charms" / "artifacts.yaml",
        "filter_by_tag": ["k8s"],
        "to_channel": "beta",
        "from_channel": "edge",
    }
    artifacts = yaml.safe_load(
        (Path("tests") / "data" / "ci-testing-charms.inc").read_text()
    )
    charm_name, charm_opts = next(iter(artifacts[0].items()))
    charm_entity = charms.BuildEntity(charm_env, charm_name, charm_opts, "ch")
    assert charm_entity.legacy_charm is False, "Initializes as false"
    charm_entity.setup()
    assert charm_entity.legacy_charm is True, "test charm requires legacy builds"


def test_build_entity_has_changed(test_environment, charm_cmd):
    """Tests has_changed property."""
    charm_env = charms.BuildEnv(build_type=charms.BuildType.CHARM)
    charm_env.db["build_args"] = {
        "artifact_list": Path(__file__).parent / "test_charms" / "artifacts.yaml",
        "filter_by_tag": ["k8s"],
        "to_channel": "edge",
        "from_channel": "beta",
    }
    charm_env.db["pull_layer_manifest"] = []
    artifacts = yaml.safe_load(
        (Path("tests") / "data" / "ci-testing-charms.inc").read_text()
    )
    charm_name, charm_opts = next(iter(artifacts[0].items()))
    charm_entity = charms.BuildEntity(charm_env, charm_name, charm_opts, "cs")
    charm_cmd.show.assert_called_once_with(
        "cs:~containers/calico", "--channel", "edge", "id"
    )
    charm_cmd.show.reset_mock()
    with patch("charms.BuildEntity.commit", new_callable=PropertyMock) as commit:
        # Test non-legacy charms with the commit rev checked in with charm matching
        commit.return_value = "96b4e06d5d35fec30cdf2cc25076dd25c51b893c"
        assert charm_entity.has_changed is False
        charm_cmd.show.assert_called_once_with(
            "cs:~containers/calico-845", "extra-info", format="yaml"
        )
        charm_cmd.show.reset_mock()

        # Test non-legacy charms with the commit rev checked in with charm not matching
        commit.return_value = "96b4e06d5d35fec30cdf2cc25076dd25c51b893d"
        assert charm_entity.has_changed is True
        charm_cmd.show.assert_called_once_with(
            "cs:~containers/calico-845", "extra-info", format="yaml"
        )
        charm_cmd.show.reset_mock()

        # Test legacy charms by comparing charmstore .build.manifest
        charm_entity.legacy_charm = True
        assert charm_entity.has_changed is True
        charm_cmd.show.assert_not_called()
        charm_cmd.show.reset_mock()

    # Test all charmhub charms comparing .build.manifest to revision
    charm_entity = charms.BuildEntity(charm_env, charm_name, charm_opts, "ch")
    charm_cmd.show.assert_not_called()
    with patch("charms.BuildEntity.commit", new_callable=PropertyMock) as commit:
        commit.return_value = "96b4e06d5d35fec30cdf2cc25076dd25c51b893c"
        assert charm_entity.has_changed is True


def test_build_entity_charm_build(test_environment, charm_cmd, charmcraft_cmd, tmpdir):
    """Test that BuildEntity runs charm_build."""
    charm_env = charms.BuildEnv(build_type=charms.BuildType.CHARM)
    charm_env.db["build_args"] = {
        "artifact_list": Path(__file__).parent / "test_charms" / "artifacts.yaml",
        "filter_by_tag": ["k8s"],
        "to_channel": "edge",
        "from_channel": "beta",
    }
    artifacts = yaml.safe_load(
        (Path("tests") / "data" / "ci-testing-charms.inc").read_text()
    )
    charm_name, charm_opts = next(iter(artifacts[0].items()))
    charm_entity = charms.BuildEntity(charm_env, charm_name, charm_opts, "ch")

    charm_entity.legacy_charm = True
    charm_entity.charm_build()
    assert charm_entity.dst_path == tmpdir / "charms" / "calico" / "calico.charm"
    charm_cmd.build.assert_called_once_with(
        "-r",
        "--force",
        "-i",
        "https://localhost",
        "--charm-file",
        _cwd=tmpdir / "charms" / "calico",
        _out=charm_entity.echo,
    )
    charmcraft_cmd.build.assert_not_called()
    charm_cmd.build.reset_mock()

    charm_entity = charms.BuildEntity(charm_env, charm_name, charm_opts, "cs")

    charm_entity.legacy_charm = True
    charm_entity.charm_build()
    assert charm_entity.dst_path == tmpdir / "build" / "calico"
    charm_cmd.build.assert_called_once_with(
        "-r",
        "--force",
        "-i",
        "https://localhost",
        _cwd=tmpdir / "charms" / "calico",
        _out=charm_entity.echo,
    )
    charmcraft_cmd.build.assert_not_called()
    charm_cmd.build.reset_mock()

    charm_entity.legacy_charm = False
    charm_entity.charm_build()
    charm_cmd.build.assert_not_called()
    charmcraft_cmd.build.assert_called_once_with(
        "-f",
        f"{tmpdir / 'charms' / 'calico'}",
        _cwd=tmpdir / "build",
        _out=charm_entity.echo,
    )


#   --------------------------------------------------
#  test click command functions


@pytest.fixture()
def mock_build_env():
    """Create a fixture defining a mock BuildEnv object."""
    with patch("charms.BuildEnv") as mock_env:
        mock_env_inst = mock_env.return_value
        mock_env_inst.db = {}
        yield mock_env_inst


@pytest.fixture()
def mock_build_entity():
    """Create a fixture defining a mock BuildEntity object."""
    with patch("charms.BuildEntity") as mock_ent:
        yield mock_ent


def test_promote_command(mock_build_env):
    """Tests cli promote command which is run by jenkins job."""
    runner = CliRunner()
    result = runner.invoke(
        charms.promote,
        [
            "--charm-list=test-charm",
            "--filter-by-tag=tag1",
            "--filter-by-tag=tag2",
            "--from-channel=unpublished",
            "--to-channel=edge",
            "--store=CH",
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
        from_channel="unpublished", to_channel="edge", store="ch"
    )


def test_build_command(mock_build_env, mock_build_entity):
    """Tests cli build command which is run by jenkins job."""
    runner = CliRunner()
    mock_build_env.artifacts = [
        {
            "calico": dict(
                tags=["tag1", "k8s"],
                namespace="containers",
                downstream="charmed-kubernetes/layer-calico.git",
            ),
            "ignored": dict(tags=["ignore-me"]),
        }
    ]
    entity = mock_build_entity.return_value
    result = runner.invoke(
        charms.build,
        [
            "--charm-list=tests/data/ci-testing-charms.inc",
            "--resource-spec=jobs/build-charms/resource-spec.yaml",
            "--filter-by-tag=tag1",
            "--filter-by-tag=tag2",
            "--layer-index=https://charmed-kubernetes.github.io/layer-index/",
            "--layer-list=jobs/includes/charm-layer-list.inc",
            "--force",
        ],
    )
    assert result.exit_code == 0, result.stdout
    assert mock_build_env.db["build_args"] == {
        "artifact_list": "tests/data/ci-testing-charms.inc",
        "layer_list": "jobs/includes/charm-layer-list.inc",
        "charm_branch": "master",
        "layer_branch": "master",
        "layer_index": "https://charmed-kubernetes.github.io/layer-index/",
        "resource_spec": "jobs/build-charms/resource-spec.yaml",
        "filter_by_tag": ["tag1", "tag2"],
        "to_channel": "edge",
        "force": True,
    }
    mock_build_env.pull_layers.assert_called_once_with()
    mock_build_env.save.assert_called_once_with()

    entity.echo.assert_has_calls(
        [
            call("Starting"),
            call(f"Details: {entity}"),
            call("Stopping"),
        ],
        any_order=False,
    )
    entity.setup.assert_called_once_with()
    entity.charm_build.assert_called_once_with()
    entity.push.assert_called_once_with()
    entity.attach_resources.assert_called_once_with()
    entity.promote.assert_called_once_with(to_channel="edge")
