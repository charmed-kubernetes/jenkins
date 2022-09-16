"""Tests to verify jobs/build-charms/charms."""

import os
import shutil
from pathlib import Path
from zipfile import ZipFile
import yaml

import pytest
from types import SimpleNamespace
from unittest.mock import patch, call, Mock, MagicMock
from functools import partial

from click.testing import CliRunner

TEST_PATH = Path(__file__).parent.parent.parent
STATIC_TEST_PATH = TEST_PATH / "data"
K8S_CI_CHARM = STATIC_TEST_PATH / "charms" / "k8s-ci-charm"
K8S_CI_BUNDLE = STATIC_TEST_PATH / "bundles" / "test-kubernetes"
CI_TESTING_CHARMS = STATIC_TEST_PATH / "ci-testing-charms.inc"
CI_TESTING_BUNDLES = STATIC_TEST_PATH / "ci-testing-bundles.inc"
CLI_RESPONSES = STATIC_TEST_PATH / "cli_response"
CHARMCRAFT_LIB_SH = TEST_PATH.parent / "jobs" / "build-charms" / "charmcraft-lib.sh"


@pytest.mark.parametrize(
    "risk, expected",
    [
        ("edge", "2.14/edge"),
        ("stable", "0.15/stable"),
        ("candidate", None),
    ],
)
def test_matched_numerical_channel(charms, risk, expected):
    track_map = {
        "0.15": ["0.15/edge", "0.15/beta", "0.15/stable"],
        "2.14": ["2.14/edge", "2.14/beta"],
    }
    assert charms.matched_numerical_channel(risk, track_map) == expected


def test_build_env_missing_env(charms):
    """Ensure missing environment variables raise Exception."""
    with pytest.raises(charms.BuildException) as ie:
        charms.BuildEnv()
    assert "build environment variables" in str(ie.value)


@pytest.fixture()
def test_environment(tmpdir):
    """Creates a fixture defining test environment variables."""
    saved_env, test_env = {}, dict(
        BUILD_TAG="jenkins-build-charms-1234",
        CHARM_BASE_DIR=str(tmpdir),
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
def cilib_store(charms):
    """Create a fixture defining mock for cilib Store."""
    with patch("charms.Store") as store:
        yield store


@pytest.fixture(autouse=True)
def github_repository(charms):
    """Create a fixture defining mock for github api."""
    with patch.object(charms, "Repository") as repo:
        yield repo.with_session.return_value


@pytest.fixture(autouse=True)
def charm_cmd():
    """Create a fixture defining mock for `charm` cli command."""

    def command_response(cmd, *args, **_kwargs):
        assert cmd == "build"  # this is the only charm command which should be run
        entity_fname, *_ = args
        entity_fname = entity_fname[4:].replace("/", "_")
        fpath = CLI_RESPONSES / f"charm_{cmd}_{entity_fname}.yaml"
        stdout = fpath.read_bytes() if fpath.exists() else b""
        return SimpleNamespace(
            stdout=stdout,
            stderr=b"",
            exit_code=0,
        )

    with patch("sh.charm", create=True) as charm:
        charm.version.return_value = '{"charm-tools": {"version": "1.2.3"}}'
        cmd = charm.bake.return_value
        cmd.build.side_effect = partial(command_response, "build")
        yield cmd


@pytest.fixture(autouse=True)
def charmhub_info():
    """Create a fixture defining mock for Charmhub info."""

    def command_response(entity_fname, **_kwargs):
        fpath = CLI_RESPONSES / f"charmhub_info_{entity_fname}.yaml"
        if fpath.exists():
            return yaml.safe_load(fpath.read_text())
        return {}

    with patch("charms._CharmHub.info", side_effect=command_response) as mock_info:
        yield mock_info


@pytest.fixture(autouse=True)
def charmcraft_cmd():
    """Create a fixture defining mock for `charmcraft` cli command."""

    def command_response(*args, **_kwargs):
        fname = "_".join(("charmcraft",) + args)
        fpath = CLI_RESPONSES / f"{fname}.txt"
        stdout = fpath.read_bytes() if fpath.exists() else b""
        return SimpleNamespace(
            stdout=stdout,
            stderr=b"",
            exit_code=0,
        )

    with patch("sh.charmcraft", create=True) as charmcraft:
        cmd = charmcraft.bake.return_value
        cmd.side_effect = command_response
        cmd.status.side_effect = partial(command_response, "status")
        cmd.resources.side_effect = partial(command_response, "resources")
        cmd.revisions.side_effect = partial(command_response, "revisions")
        cmd.pack.side_effect = partial(command_response, "pack")
        yield cmd


@pytest.fixture()
def bundle_environment(test_environment, charms):
    charm_env = charms.BuildEnv(build_type=charms.BuildType.BUNDLE)
    charm_env.db["build_args"] = {
        "artifact_list": str(CI_TESTING_BUNDLES),
        "branch": "main",
        "filter_by_tag": ["k8s"],
        "to_channel": "edge",
    }
    charm_env.db["pull_layer_manifest"] = []
    yield charm_env


@pytest.fixture()
def charm_environment(test_environment, charms):
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


def test_build_env_promote_all_charmhub(charm_environment, charmcraft_cmd):
    """Tests promote_all to charmhub."""
    charm_environment.promote_all(
        from_channel="latest/edge", to_channels=["latest/beta"]
    )
    resource_args = [
        "--resource=test-file:994",
        "--resource=test-file-2:993",
    ]
    charmcraft_cmd.release.assert_called_once_with(
        "k8s-ci-charm", "--revision=845", "--channel=latest/beta", *resource_args
    )


@patch("charms.os.makedirs", Mock())
@patch("charms.cmd_ok")
def test_build_entity_setup(cmd_ok, charm_environment, tmpdir, charms):
    """Tests build entity setup."""
    artifacts = charm_environment.artifacts
    charm_name, charm_opts = next(iter(artifacts[0].items()))
    charm_entity = charms.BuildEntity(charm_environment, charm_name, charm_opts)
    assert charm_entity.reactive is False, "Initializes as false"
    charm_entity.setup()
    assert charm_entity.reactive is True, "test charm requires legacy builds"
    cmd_ok.assert_called_once_with(
        f"git clone --branch main https://github.com/charmed-kubernetes/jenkins.git {charm_entity.checkout_path}",
        echo=charm_entity.echo,
    )


def test_build_entity_has_changed(charm_environment, charm_cmd, charms):
    """Tests has_changed property."""
    artifacts = charm_environment.artifacts
    charm_name, charm_opts = next(iter(artifacts[0].items()))
    charm_entity = charms.BuildEntity(charm_environment, charm_name, charm_opts)
    with patch("charms.BuildEntity.commit") as commit:
        # Test non-legacy charms with the commit rev checked in with charm matching
        commit.return_value = "51b893c"
        assert charm_entity.has_changed is False

        # Test non-legacy charms with the commit rev checked in with charm not matching
        commit.return_value = "51b893d"
        assert charm_entity.has_changed is True

        # Test legacy charms by comparing charmstore .build.manifest
        charm_entity.reactive = True
        assert charm_entity.has_changed is True


@patch("charms.script")
def test_build_entity_charm_build(
    mock_script, charm_environment, charm_cmd, charmcraft_cmd, tmpdir, charms
):
    """Test that BuildEntity runs charm_build."""
    artifacts = charm_environment.artifacts
    charm_name, charm_opts = next(iter(artifacts[0].items()))

    charm_entity = charms.BuildEntity(charm_environment, charm_name, charm_opts)

    # Charms built with override
    charm_entity.opts["override-build"] = MagicMock()
    charm_entity.charm_build()
    charm_cmd.build.assert_not_called()
    charmcraft_cmd.build.assert_not_called()
    mock_script.assert_called_once_with(
        charm_entity.opts["override-build"],
        cwd=charm_entity.src_path,
        charm=charm_entity.name,
        echo=charm_entity.echo,
    )
    mock_script.reset_mock()
    del charm_entity.opts["override-build"]

    # Reactive charms built with charm tools
    charm_entity.reactive = True
    charm_entity.charm_build()

    manifest_yaml = Path(charm_entity.src_path, "manifest.yaml")
    assert manifest_yaml.exists(), "Manifest not generated"
    manifest_yaml.unlink()

    assert charm_entity.dst_path == str(K8S_CI_CHARM / "k8s-ci-charm.charm")
    charm_cmd.build.assert_called_once_with(
        "-r",
        "--force",
        "-i",
        "https://localhost",
        "--charm-file",
        _cwd=str(K8S_CI_CHARM),
    )
    mock_script.assert_not_called()
    charmcraft_cmd.build.assert_not_called()
    charm_cmd.build.reset_mock()

    # Operator Charms, build with charmcraft container
    charm_entity.reactive = False
    os.environ["charmcraft_lxc"] = "unnamed-job-0"
    charm_entity.charm_build()
    charm_cmd.build.assert_not_called()
    mock_script.assert_called_once_with(
        "#!/bin/bash -eux\n"
        f"source {CHARMCRAFT_LIB_SH}\n"
        f"ci_charmcraft_pack unnamed-job-0 https://github.com/{charm_entity.downstream} main \n"
        f"ci_charmcraft_copy unnamed-job-0 {K8S_CI_CHARM}/k8s-ci-charm.charm\n",
        echo=charm_entity.echo,
    )
    mock_script.reset_mock()

    # Operator Charms, fail build without charmcraft container
    del os.environ["charmcraft_lxc"]
    with pytest.raises(charms.BuildException):
        charm_entity.charm_build()


def test_build_entity_push(
    charm_environment, charm_cmd, charmcraft_cmd, tmpdir, charms, github_repository
):
    """Test that BuildEntity pushes to appropriate store."""
    artifacts = charm_environment.artifacts
    charm_name, charm_opts = next(iter(artifacts[0].items()))

    charmcraft_cmd.upload.return_value.stdout = (
        CLI_RESPONSES / "charmcraft_upload_k8s-ci-charm.txt"
    ).read_bytes()

    charm_entity = charms.BuildEntity(charm_environment, charm_name, charm_opts)
    charm_entity.commit = MagicMock(return_value="deadbeef")
    charm_entity.push()
    charm_cmd.push.assert_not_called()
    charmcraft_cmd.upload.assert_called_once_with(charm_entity.dst_path)
    charm_entity.commit.assert_called_once_with()
    github_repository.tag_commit.assert_called_once_with(
        "deadbeef", tag='k8s-ci-charm-845', message='Built by job: jenkins-build-charms-1234'
    )
    assert charm_entity.new_entity == "845"


@patch("charms.os.makedirs", Mock())
def test_build_entity_attach_resource(
    charm_environment, charm_cmd, charmcraft_cmd, tmpdir, charms
):
    artifacts = charm_environment.artifacts
    charm_name, charm_opts = next(iter(artifacts[0].items()))

    charm_entity = charms.BuildEntity(charm_environment, charm_name, charm_opts)
    charm_entity.dst_path = charm_entity.src_path
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
            ),
            call(
                "upload-resource",
                "k8s-ci-charm",
                "test-image",
                image="test-image",
            ),
        ],
        any_order=False,
    )
    charm_cmd.assert_not_called()


def test_build_entity_promote(
    charm_environment, charm_cmd, charmcraft_cmd, tmpdir, charms
):
    """Test that BuildEntity releases to appropriate store."""
    artifacts = charm_environment.artifacts
    charm_name, charm_opts = next(iter(artifacts[0].items()))

    charm_entity = charms.BuildEntity(charm_environment, charm_name, charm_opts)
    charm_entity.promote(to_channels=("edge", "0.15/edge"))
    charm_cmd.release.assert_not_called()
    charmcraft_cmd.release.assert_called_once_with(
        "k8s-ci-charm",
        "--revision=6",
        "--channel=latest/edge",
        "--channel=0.15/edge",
        "--resource=test-file:3",
        "--resource=test-image:4",
    )
    charmcraft_cmd.release.reset_mock()

    charm_entity.promote(to_channels=("stable", "0.15/stable"))
    charm_cmd.release.assert_not_called()
    charmcraft_cmd.release.assert_called_once_with(
        "k8s-ci-charm",
        "--revision=6",
        "--channel=latest/stable",
        "--channel=0.15/stable",
        "--resource=test-file:3",
        "--resource=test-image:4",
    )
    charmcraft_cmd.release.reset_mock()
    charm_entity.promote(to_channels=("0.14/stable",))
    charm_cmd.release.assert_not_called()
    charmcraft_cmd.release.assert_called_once_with(
        "k8s-ci-charm",
        "--revision=6",
        "--channel=0.14/stable",
        "--resource=test-file:3",
        "--resource=test-image:4",
    )
    charmcraft_cmd.release.reset_mock()


def test_bundle_build_entity_push(
    bundle_environment, charm_cmd, charmcraft_cmd, tmpdir, charms
):
    """Test that BundleBuildEntity pushes to appropriate store."""
    artifacts = bundle_environment.artifacts
    bundle_name, bundle_opts = next(iter(artifacts[0].items()))

    bundle_opts["src_path"] = bundle_environment.default_repo_dir
    bundle_opts["dst_path"] = bundle_environment.bundles_dir / bundle_name
    charmcraft_cmd.upload.return_value.stdout = (
        CLI_RESPONSES / "charmcraft_upload_test-kubernetes.txt"
    ).read_bytes()
    bundle_entity = charms.BundleBuildEntity(
        bundle_environment, bundle_name, bundle_opts
    )
    bundle_entity.push()
    charm_cmd.push.assert_not_called()
    charmcraft_cmd.upload.assert_called_once_with(bundle_entity.dst_path)
    assert bundle_entity.new_entity == "123"


@patch("charms.cmd_ok")
def test_bundle_build_entity_bundle_build(
    cmd_ok, charmcraft_cmd, bundle_environment, charms
):
    """Tests bundle_build method."""
    artifacts = bundle_environment.artifacts
    bundle_name, bundle_opts = next(iter(artifacts[0].items()))
    bundle_opts["src_path"] = K8S_CI_BUNDLE
    bundle_opts["dst_path"] = dst_path = bundle_environment.bundles_dir / bundle_name

    # Test a bundle copy takes place
    # Test that a bundle pack occurs
    bundle_opts["skip-build"] = True
    bundle_entity = charms.BundleBuildEntity(
        bundle_environment, bundle_name, bundle_opts
    )
    bundle_entity.bundle_build("edge")
    charmcraft_cmd.pack.assert_called_once_with(_cwd=dst_path)
    assert (
        bundle_entity.dst_path
        == "/not/real/path/to/scratch/tmp/bundles/test-kubernetes.zip"
    )
    assert (dst_path / "bundle.yaml").exists()
    assert (dst_path / "tests" / "test.yaml").exists()
    cmd_ok.assert_not_called()
    bundle_entity.reset_dst_path()
    dst_path.mkdir()

    # Test a bundle build takes place
    del bundle_opts["skip-build"]
    bundle_entity = charms.BundleBuildEntity(
        bundle_environment, bundle_name, bundle_opts
    )
    bundle_entity.bundle_build("edge")
    assert not (dst_path / "bundle.yaml").exists()
    cmd = f"{K8S_CI_BUNDLE / 'bundle'} -n test-kubernetes -o {dst_path} -c edge k8s/core cni/flannel cri/containerd"
    cmd_ok.assert_called_with(cmd, echo=bundle_entity.echo)
    cmd_ok.reset_mock()
    shutil.rmtree(dst_path)


def test_bundle_build_entity_has_changed(bundle_environment, charm_cmd, charms):
    """Tests has_changed property."""
    artifacts = bundle_environment.artifacts
    bundle_name, bundle_opts = next(iter(artifacts[0].items()))
    bundle_opts["src_path"] = bundle_environment.default_repo_dir
    bundle_opts["dst_path"] = K8S_CI_BUNDLE.with_suffix(".bundle")

    # Test all charmhub charms comparing .build.manifest to revision
    bundle_entity = charms.BundleBuildEntity(
        bundle_environment, bundle_name, bundle_opts
    )
    with patch.object(
        bundle_entity, "download", return_value=MagicMock(autospec=ZipFile)
    ):
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
def mock_bundle_build_entity(charms):
    """Create a fixture defining a mock BundleBuildEntity object."""
    spec = dir(charms.BundleBuildEntity)
    with patch("charms.BundleBuildEntity") as mock_ent:

        def create_mock_bundle(*args):
            mm = MagicMock(spec=spec)
            mm.build, mm.name, mm.opts = args
            mock_ent.entities.append(mm)
            return mm

        mock_ent.side_effect = create_mock_bundle
        mock_ent.entities = []
        yield mock_ent


def test_promote_command(mock_build_env, charms):
    """Tests cli promote command which is run by jenkins job."""
    runner = CliRunner()
    result = runner.invoke(
        charms.promote,
        [
            "--charm-list=test-charm",
            "--filter-by-tag=tag1,tag2",
            "--from-channel=latest/edge",
            "--to-channel=latest/beta",
        ],
    )
    if result.exception:
        raise result.exception
    assert mock_build_env.db["build_args"] == {
        "artifact_list": "test-charm",
        "filter_by_tag": ["tag1", "tag2"],
        "from_channel": "latest/edge",
        "to_channel": "latest/beta",
        "track": "latest",
    }
    mock_build_env.promote_all.assert_called_once_with(
        from_channel="latest/edge",
        to_channels=mock_build_env.to_channels,
    )


def test_build_command(mock_build_env, mock_build_entity, charms):
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
    mock_build_env.filter_by_tag = ["tag1", "tag2"]
    entity = mock_build_entity.return_value
    result = runner.invoke(
        charms.build,
        [
            "--charm-list=tests/data/ci-testing-charms.inc",
            "--resource-spec=jobs/build-charms/resource-spec.yaml",
            "--filter-by-tag=tag1,tag2",
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
        "branch": "",
        "layer_branch": "main",
        "layer_index": "https://charmed-kubernetes.github.io/layer-index/",
        "resource_spec": "jobs/build-charms/resource-spec.yaml",
        "filter_by_tag": mock_build_env.filter_by_tag,
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
            call("Build forced."),
            call("Stopping"),
        ],
        any_order=False,
    )
    entity.setup.assert_called_once_with()
    entity.charm_build.assert_called_once_with()
    entity.push.assert_called_once_with()
    entity.attach_resources.assert_called_once_with()
    entity.promote.assert_called_once_with(to_channels=mock_build_env.to_channels)


@patch("charms.cmd_ok")
def test_bundle_build_command(
    cmd_ok, mock_build_env, mock_bundle_build_entity, tmpdir, charms
):
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
    mock_build_env.to_channels = ("edge", "0.15/edge")
    mock_build_env.filter_by_tag = ["k8s"]
    mock_build_env.force = False

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
        "branch": "main",
        "filter_by_tag": mock_build_env.filter_by_tag,
        "track": "latest",
        "to_channel": "edge",
        "force": False,
    }
    cmd_ok.assert_called_once_with(
        f"git clone --branch main https://github.com/charmed-kubernetes/bundle.git {mock_build_env.default_repo_dir}"
    )
    mock_build_env.pull_layers.assert_not_called()
    mock_build_env.save.assert_called_once_with()

    for entity in mock_bundle_build_entity.entities:
        entity.echo.assert_has_calls(
            [
                call("Starting"),
                call(f"Details: {entity}"),
                call("Pushing built bundle for channel=edge (forced=False)."),
                call("Pushing built bundle for channel=0.15/edge (forced=False)."),
                call("Stopping"),
            ],
            any_order=False,
        )
        if "downstream" in entity.opts:
            entity.setup.assert_called_once_with()

        assert entity.bundle_build.mock_calls == [
            call(channel) for channel in mock_build_env.to_channels
        ]
        assert entity.push.mock_calls == [call(), call()]
        assert entity.promote.mock_calls == [
            call(to_channels=[channel]) for channel in mock_build_env.to_channels
        ]
        assert entity.reset_dst_path.mock_calls == [call(), call()]
