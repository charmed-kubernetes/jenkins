"""Tests to verify jobs/build-charms/charms."""

import os
import re
from pathlib import Path

import pytest
from types import SimpleNamespace
from unittest.mock import patch, call, Mock, MagicMock, PropertyMock
from functools import partial

from click.testing import CliRunner
import charms

STATIC_TEST_PATH = Path(__file__).parent.parent.parent / "data"
K8S_CI_CHARM = STATIC_TEST_PATH / "charms" / "k8s-ci-charm"
K8S_CI_BUNDLE = STATIC_TEST_PATH / "bundles" / "test-kubernetes"
CI_TESTING_CHARMS = STATIC_TEST_PATH / "ci-testing-charms.inc"
CI_TESTING_BUNDLES = STATIC_TEST_PATH / "ci-testing-bundles.inc"
CLI_RESPONSES = STATIC_TEST_PATH / "cli_response"


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
        CHARM_CHARMS_DIR=f'{STATIC_TEST_PATH / "charms"}',
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

    def charm_command_response(cmd, *args, **_kwargs):
        entity_fname = None
        if cmd == "push":
            _directory, entity_fname = args
        elif cmd == "show":
            charm_or_bundle_id, *fields = args
            entity_fname = re.split(r"(-\d+)$", charm_or_bundle_id)[0]
        elif cmd == "list-resources":
            (entity_fname,) = args

        if entity_fname:
            entity_fname = entity_fname[4:].replace("/", "_")
            return SimpleNamespace(
                stdout=(CLI_RESPONSES / f"charm_{cmd}_{entity_fname}.yaml").read_bytes()
            )

    with patch("sh.charm", create=True) as charm:
        charm.side_effect = charm_command_response
        charm.show.side_effect = partial(charm_command_response, "show")
        charm.push.side_effect = partial(charm_command_response, "push")
        yield charm


@pytest.fixture(autouse=True)
def charmcraft_cmd():
    """Create a fixture defining mock for `charmcraft` cli command."""
    with patch("sh.charmcraft", create=True) as cmd:
        cmd.status.return_value.stdout = (
            CLI_RESPONSES / "charmcraft_status_k8s-ci-charm.txt"
        ).read_bytes()
        cmd.resources.return_value.stdout = (
            CLI_RESPONSES / "charmcraft_resources_k8s-ci-charm.txt"
        ).read_bytes()
        cmd.revisions.return_value.stdout = (
            CLI_RESPONSES / "charmcraft_revisions_k8s-ci-charm.txt"
        ).read_bytes()

        def hyphened_commands(*args, **_kwargs):
            command, *cmd_args = args
            if command == "resource-revisions":
                _, resource = cmd_args
                return SimpleNamespace(
                    stdout=(
                        CLI_RESPONSES
                        / f"charmcraft_resource_revisions_k8s-ci-charm_{resource}.txt"
                    ).read_bytes()
                )
            elif command == "upload-resource":
                return
            pass

        cmd.side_effect = hyphened_commands
        yield cmd


@pytest.fixture()
def bundle_environment(test_environment):
    charm_env = charms.BuildEnv(build_type=charms.BuildType.BUNDLE)
    charm_env.db["build_args"] = {
        "artifact_list": str(CI_TESTING_BUNDLES),
        "branch": "master",
        "filter_by_tag": ["k8s"],
        "to_channel": "edge",
    }
    charm_env.db["pull_layer_manifest"] = []
    yield charm_env


@pytest.fixture()
def charm_environment(test_environment):
    charm_env = charms.BuildEnv(build_type=charms.BuildType.CHARM)
    charm_env.db["build_args"] = {
        "artifact_list": str(CI_TESTING_CHARMS),
        "filter_by_tag": ["k8s"],
        "to_channel": "edge",
        "from_channel": "beta",
        "resource_spec": str(STATIC_TEST_PATH / "ci-testing-resource-spec.yaml"),
    }
    charm_env.db["pull_layer_manifest"] = []
    yield charm_env


def test_build_env_promote_all_charmstore(charm_environment, cilib_store, charm_cmd):
    """Test promote_all to the charmstore."""
    charm_environment.promote_all()
    charm_entity = "cs:~containers/k8s-ci-charm"
    charm_entity_ver = f"{charm_entity}-845"
    charm_cmd.show.assert_called_once_with(
        charm_entity, "id", channel="unpublished", _tee=True
    )
    charm_cmd.assert_called_once_with(
        "list-resources",
        charm_entity_ver,
        channel="unpublished",
        format="yaml",
        _tee=True,
    )
    resource_args = [
        ("--resource", "test-file-995"),
        ("--resource", "test-image-995"),
    ]
    charm_cmd.release.assert_called_once_with(
        charm_entity_ver, "--channel=edge", *resource_args, _out=charm_environment.echo
    )


def test_build_env_promote_all_charmhub(charm_environment, charmcraft_cmd):
    """Tests promote_all to charmhub."""
    charm_environment.promote_all(from_channel="edge", to_channel="beta", store="ch")
    resource_args = [
        "--resource=test-file:994",
        "--resource=test-file-2:993",
    ]
    charmcraft_cmd.release.assert_called_once_with(
        "k8s-ci-charm", "--revision=845", "--channel=beta", *resource_args, _tee=True
    )


@patch("charms.os.makedirs", Mock())
@patch("charms.cmd_ok")
def test_build_entity_setup(cmd_ok, charm_environment, tmpdir):
    """Tests build entity setup."""
    artifacts = charm_environment.artifacts
    charm_name, charm_opts = next(iter(artifacts[0].items()))
    charm_entity = charms.BuildEntity(charm_environment, charm_name, charm_opts, "ch")
    assert charm_entity.legacy_charm is False, "Initializes as false"
    charm_entity.setup()
    assert charm_entity.legacy_charm is True, "test charm requires legacy builds"
    cmd_ok.assert_called_once_with(
        f"git clone --branch master https://github.com/charmed-kubernetes/jenkins.git {charm_entity.checkout_path}",
        echo=charm_entity.echo,
    )


def test_build_entity_has_changed(charm_environment, charm_cmd):
    """Tests has_changed property."""
    artifacts = charm_environment.artifacts
    charm_name, charm_opts = next(iter(artifacts[0].items()))
    charm_entity = charms.BuildEntity(charm_environment, charm_name, charm_opts, "cs")
    charm_cmd.show.assert_called_once_with(
        "cs:~containers/k8s-ci-charm", "id", channel="edge", _tee=True
    )
    charm_cmd.show.reset_mock()
    with patch("charms.BuildEntity.commit", new_callable=PropertyMock) as commit:
        # Test non-legacy charms with the commit rev checked in with charm matching
        commit.return_value = "96b4e06d5d35fec30cdf2cc25076dd25c51b893c"
        assert charm_entity.has_changed is False
        charm_cmd.show.assert_called_once_with(
            "cs:~containers/k8s-ci-charm-845", "extra-info", format="yaml"
        )
        charm_cmd.show.reset_mock()

        # Test non-legacy charms with the commit rev checked in with charm not matching
        commit.return_value = "96b4e06d5d35fec30cdf2cc25076dd25c51b893d"
        assert charm_entity.has_changed is True
        charm_cmd.show.assert_called_once_with(
            "cs:~containers/k8s-ci-charm-845", "extra-info", format="yaml"
        )
        charm_cmd.show.reset_mock()

        # Test legacy charms by comparing charmstore .build.manifest
        charm_entity.legacy_charm = True
        assert charm_entity.has_changed is True
        charm_cmd.show.assert_not_called()
        charm_cmd.show.reset_mock()

    # Test all charmhub charms comparing .build.manifest to revision
    charm_entity = charms.BuildEntity(charm_environment, charm_name, charm_opts, "ch")
    charm_cmd.show.assert_not_called()
    with patch("charms.BuildEntity.commit", new_callable=PropertyMock) as commit:
        commit.return_value = "96b4e06d5d35fec30cdf2cc25076dd25c51b893c"
        assert charm_entity.has_changed is True


def test_build_entity_charm_build(charm_environment, charm_cmd, charmcraft_cmd, tmpdir):
    """Test that BuildEntity runs charm_build."""
    artifacts = charm_environment.artifacts
    charm_name, charm_opts = next(iter(artifacts[0].items()))
    charm_entity = charms.BuildEntity(charm_environment, charm_name, charm_opts, "ch")

    charm_entity.legacy_charm = True
    charm_entity.charm_build()
    assert charm_entity.dst_path == K8S_CI_CHARM / "k8s-ci-charm.charm"
    charm_cmd.build.assert_called_once_with(
        "-r",
        "--force",
        "-i",
        "https://localhost",
        "--charm-file",
        _cwd=str(K8S_CI_CHARM),
        _out=charm_entity.echo,
    )
    charmcraft_cmd.build.assert_not_called()
    charm_cmd.build.reset_mock()

    charm_entity = charms.BuildEntity(charm_environment, charm_name, charm_opts, "cs")

    charm_entity.legacy_charm = True
    charm_entity.charm_build()
    assert charm_entity.dst_path == tmpdir / "build" / "k8s-ci-charm"
    charm_cmd.build.assert_called_once_with(
        "-r",
        "--force",
        "-i",
        "https://localhost",
        _cwd=str(K8S_CI_CHARM),
        _out=charm_entity.echo,
    )
    charmcraft_cmd.build.assert_not_called()
    charm_cmd.build.reset_mock()

    charm_entity.legacy_charm = False
    charm_entity.charm_build()
    charm_cmd.build.assert_not_called()
    charmcraft_cmd.build.assert_called_once_with(
        "-f",
        str(K8S_CI_CHARM),
        _cwd=tmpdir / "build",
        _out=charm_entity.echo,
    )


def test_build_entity_push(charm_environment, charm_cmd, charmcraft_cmd, tmpdir):
    """Test that BuildEntity pushes to appropriate store."""
    artifacts = charm_environment.artifacts
    charm_name, charm_opts = next(iter(artifacts[0].items()))

    with patch("charms.BuildEntity.commit", new_callable=PropertyMock) as commit:
        charm_entity = charms.BuildEntity(
            charm_environment, charm_name, charm_opts, "cs"
        )
        commit.return_value = "96b4e06d5d35fec30cdf2cc25076dd25c51b893c"
        charm_entity.push()
    charmcraft_cmd.upload.assert_not_called()
    charm_cmd.push.assert_called_once_with(
        charm_entity.dst_path, "cs:~containers/k8s-ci-charm", _tee=True
    )
    charm_cmd.set.assert_called_once_with(
        "cs:~containers/k8s-ci-charm-845",
        "commit=96b4e06d5d35fec30cdf2cc25076dd25c51b893c",
        _out=charm_entity.echo,
    )
    assert charm_entity.new_entity == "cs:~containers/k8s-ci-charm-845"

    charm_cmd.push.reset_mock()
    charmcraft_cmd.upload.return_value.stdout = (
        CLI_RESPONSES / "charmcraft_upload_k8s-ci-charm.txt"
    ).read_bytes()

    charm_entity = charms.BuildEntity(charm_environment, charm_name, charm_opts, "ch")
    charm_entity.push()
    charm_cmd.push.assert_not_called()
    charmcraft_cmd.upload.assert_called_once_with(
        "-q", charm_entity.dst_path, _tee=True
    )
    assert charm_entity.new_entity == "845"


@patch("charms.os.makedirs", Mock())
def test_build_entity_attach_resource(
    charm_environment, charm_cmd, charmcraft_cmd, tmpdir
):
    artifacts = charm_environment.artifacts
    charm_name, charm_opts = next(iter(artifacts[0].items()))
    charm_entity = charms.BuildEntity(charm_environment, charm_name, charm_opts, "cs")

    with patch("charms.script") as mock_script:
        charm_entity.new_entity = charm_revision = "cs:~containers/k8s-ci-charm-845"
        charm_entity.attach_resources()
    mock_script.assert_called_once()
    charm_cmd.attach.assert_has_calls(
        [
            call(
                charm_revision,
                f"test-file={K8S_CI_CHARM / 'tmp' / 'test-file.txt'}",
                _out=charm_entity.echo,
            ),
            call(
                charm_revision,
                "test-image=test-image",
                _out=charm_entity.echo,
            ),
        ],
        any_order=False,
    )
    charmcraft_cmd.assert_not_called()

    charm_entity = charms.BuildEntity(charm_environment, charm_name, charm_opts, "ch")
    with patch("charms.script") as mock_script:
        charm_entity.attach_resources()
    mock_script.assert_called_once()
    charmcraft_cmd.assert_has_calls(
        [
            call(
                "upload-resource",
                "k8s-ci-charm",
                "test-file",
                filepath=str(K8S_CI_CHARM / "tmp" / "test-file.txt"),
                _tee=True,
            ),
            call(
                "upload-resource",
                "k8s-ci-charm",
                "test-image",
                image="test-image",
                _tee=True,
            ),
        ],
        any_order=False,
    )
    charm_cmd.assert_not_called()


def test_build_entity_promote(charm_environment, charm_cmd, charmcraft_cmd, tmpdir):
    """Test that BuildEntity releases to appropriate store."""
    artifacts = charm_environment.artifacts
    charm_name, charm_opts = next(iter(artifacts[0].items()))

    charm_entity = charms.BuildEntity(charm_environment, charm_name, charm_opts, "ch")
    charm_entity.promote(to_channel="edge")
    charm_cmd.release.assert_not_called()
    charmcraft_cmd.release.assert_called_once_with(
        "k8s-ci-charm",
        "--revision=6",
        "--channel=latest/edge",
        "--resource=test-file:3",
        "--resource=test-image:4",
        _tee=True,
    )
    charmcraft_cmd.release.reset_mock()

    charm_entity = charms.BuildEntity(charm_environment, charm_name, charm_opts, "cs")
    charm_entity.promote(to_channel="edge")
    charm_cmd.release.assert_called_once_with(
        "cs:~containers/k8s-ci-charm-845",
        "--channel=edge",
        ("--resource", "test-file-995"),
        ("--resource", "test-image-995"),
        _out=charm_entity.echo,
    )
    charm_cmd.grant.assert_called_once_with(
        "cs:~containers/k8s-ci-charm-845",
        "everyone",
        acl="read",
        _out=charm_entity.echo,
    )
    charmcraft_cmd.release.assert_not_called()


def test_bundle_build_entity_push(
    bundle_environment, charm_cmd, charmcraft_cmd, tmpdir
):
    """Test that BundleBuildEntity pushes to appropriate store."""
    artifacts = bundle_environment.artifacts
    bundle_name, bundle_opts = next(iter(artifacts[0].items()))

    with patch("charms.BuildEntity.commit", new_callable=PropertyMock) as commit:
        bundle_opts["src_path"] = bundle_environment.default_repo_dir
        bundle_opts["dst_path"] = bundle_environment.bundles_dir / bundle_name
        bundle_entity = charms.BundleBuildEntity(
            bundle_environment, bundle_name, bundle_opts, "cs"
        )
        commit.return_value = "96b4e06d5d35fec30cdf2cc25076dd25c51b893c"
        bundle_entity.push()

    charmcraft_cmd.upload.assert_not_called()
    charm_cmd.push.assert_called_once_with(
        bundle_entity.dst_path, "cs:~containers/bundle/test-kubernetes", _tee=True
    )
    charm_cmd.set.assert_called_once_with(
        "cs:~containers/bundle/test-kubernetes-123",
        "commit=96b4e06d5d35fec30cdf2cc25076dd25c51b893c",
        _out=bundle_entity.echo,
    )
    assert bundle_entity.new_entity == "cs:~containers/bundle/test-kubernetes-123"

    charm_cmd.push.reset_mock()
    charmcraft_cmd.upload.return_value.stdout = (
        CLI_RESPONSES / "charmcraft_upload_test-kubernetes.txt"
    ).read_bytes()
    bundle_entity = charms.BundleBuildEntity(
        bundle_environment, bundle_name, bundle_opts, "ch"
    )
    bundle_entity.push()
    charm_cmd.push.assert_not_called()
    charmcraft_cmd.upload.assert_called_once_with(
        "-q", bundle_entity.dst_path, _tee=True
    )
    assert bundle_entity.new_entity == "123"


@patch("charms.cmd_ok")
@patch("shutil.copytree")
def test_bundle_build_entity_bundle_build(shutil_copytree, cmd_ok, bundle_environment):
    """Tests bundle_build method."""
    artifacts = bundle_environment.artifacts
    bundle_name, bundle_opts = next(iter(artifacts[0].items()))
    bundle_opts["src_path"] = bundle_environment.default_repo_dir
    bundle_opts["dst_path"] = K8S_CI_BUNDLE

    bundle_opts["skip-build"] = True
    bundle_entity = charms.BundleBuildEntity(
        bundle_environment, bundle_name, bundle_opts, "cs"
    )
    bundle_entity.bundle_build("edge")
    shutil_copytree.assert_called_once_with(
        bundle_environment.default_repo_dir, str(K8S_CI_BUNDLE)
    )
    cmd_ok.assert_not_called()
    shutil_copytree.reset_mock()

    del bundle_opts["skip-build"]
    bundle_entity = charms.BundleBuildEntity(
        bundle_environment, bundle_name, bundle_opts, "cs"
    )
    bundle_entity.bundle_build("edge")
    shutil_copytree.assert_not_called()
    cmd = f"{bundle_environment.default_repo_dir/'bundle'} -o {K8S_CI_BUNDLE} -c edge k8s/core cni/flannel cri/containerd"
    cmd_ok.assert_called_with(cmd, echo=bundle_entity.echo)


def test_bundle_build_entity_has_changed(bundle_environment, charm_cmd):
    """Tests has_changed property."""
    artifacts = bundle_environment.artifacts
    bundle_name, bundle_opts = next(iter(artifacts[0].items()))
    bundle_opts["src_path"] = bundle_environment.default_repo_dir
    bundle_opts["dst_path"] = K8S_CI_BUNDLE

    bundle_entity = charms.BundleBuildEntity(
        bundle_environment, bundle_name, bundle_opts, "cs"
    )
    charm_cmd.show.assert_called_once_with(
        "cs:~containers/bundle/test-kubernetes", "id", channel="edge", _tee=True
    )
    assert bundle_entity.has_changed is True
    charm_cmd.show.reset_mock()

    # Test all charmhub charms comparing .build.manifest to revision
    bundle_entity = charms.BundleBuildEntity(
        bundle_environment, bundle_name, bundle_opts, "ch"
    )
    charm_cmd.show.assert_not_called()
    assert bundle_entity.has_changed is True


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


@pytest.fixture()
def mock_bundle_build_entity():
    """Create a fixture defining a mock BundleBuildEntity object."""
    spec = dir(charms.BundleBuildEntity)
    with patch("charms.BundleBuildEntity") as mock_ent:

        def create_mock_bundle(*args):
            mm = MagicMock(spec=spec)
            mm.build, mm.name, mm.opts, mm.store = args
            mock_ent.entities.append(mm)
            return mm

        mock_ent.side_effect = create_mock_bundle
        mock_ent.entities = []
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
    if result.exception:
        raise result.exception
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
            "k8s-ci-charm": dict(
                tags=["tag1", "k8s"],
                namespace="containers",
                downstream="charmed-kubernetes/layer-k8s-ci-charm.git",
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
    if result.exception:
        raise result.exception

    assert mock_build_env.db["build_args"] == {
        "artifact_list": "tests/data/ci-testing-charms.inc",
        "layer_list": "jobs/includes/charm-layer-list.inc",
        "branch": "master",
        "layer_branch": "master",
        "layer_index": "https://charmed-kubernetes.github.io/layer-index/",
        "resource_spec": "jobs/build-charms/resource-spec.yaml",
        "filter_by_tag": ["tag1", "tag2"],
        "track": "latest",
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


@patch("charms.cmd_ok")
def test_bundle_build_command(cmd_ok, mock_build_env, mock_bundle_build_entity, tmpdir):
    """Tests cli build command which is run by jenkins job."""
    runner = CliRunner()
    mock_build_env.artifacts = [
        {
            "test-kubernetes": dict(
                tags=["k8s", "canonical-kubernetes"],
                namespace="containers/bundle",
                fragments="k8s/cdk cni/flannel cri/containerd",
            ),
            "ignored": dict(tags=["ignore-me"]),
            "test-kubernetes-repo": dict(
                tags=["k8s", "addons" "test-kubernetes-repo"],
                namespace="containers",
                downstream="charmed-kubernetes/test-kubernetes-repo.git",
                **{"skip-build": True},
            ),
        }
    ]
    mock_build_env.tmp_dir = tmpdir
    mock_build_env.repos_dir = mock_build_env.tmp_dir / "repos"
    mock_build_env.bundles_dir = mock_build_env.tmp_dir / "bundles"
    mock_build_env.default_repo_dir = mock_build_env.repos_dir / "bundles-kubernetes"

    result = runner.invoke(
        charms.build_bundles,
        [
            "--bundle-list=tests/data/ci-testing-bundles.inc",
            "--filter-by-tag=k8s",
        ],
    )
    if result.exception:
        raise result.exception

    assert mock_build_env.db["build_args"] == {
        "artifact_list": "tests/data/ci-testing-bundles.inc",
        "branch": "master",
        "filter_by_tag": ["k8s"],
        "track": "latest",
        "to_channel": "edge",
    }
    cmd_ok.assert_called_once_with(
        f"git clone --branch master https://github.com/charmed-kubernetes/bundle-canonical-kubernetes.git {mock_build_env.default_repo_dir}"
    )
    mock_build_env.pull_layers.assert_not_called()
    mock_build_env.save.assert_called_once_with()

    for entity in mock_bundle_build_entity.entities:
        entity.echo.assert_has_calls(
            [
                call("Starting"),
                call(f"Details: {entity}"),
                call("Stopping"),
            ],
            any_order=False,
        )
        if "downstream" in entity.opts:
            entity.setup.assert_called_once_with()
        entity.bundle_build.assert_called_once_with("edge")
        entity.push.assert_called_once_with()
        entity.promote.assert_called_once_with(to_channel="edge")
