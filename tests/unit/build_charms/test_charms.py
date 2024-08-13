"""Tests to verify jobs/build-charms/charms."""

import os
import shutil
from pathlib import Path
from zipfile import ZipFile
import yaml

import pytest
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


architecure_test_data = [
    # a single base and single arch -- a single specific artifact
    ("charm_ubuntu-20.04-arm64.charm", "20.04", "arm64"),
    # a single base and N arches -- a single artifact for this series
    ("charm_ubuntu-20.04-arm64-amd64.charm", "20.04", "all"),
    # N bases and one arch -- a single artifact for this arch
    ("charm_ubuntu-20.04-arm64_ubuntu-22.04-arm64.charm", "all", "arm64"),
    # N bases and M arches -- a single artifact for all series and archs
    ("charm_ubuntu-20.04-arm64-amd64_ubuntu-22.04-arm64-amd64.charm", "all", "all"),
]


@pytest.mark.parametrize("filename, series, arch", architecure_test_data)
def test_artifacts_from_charm_file(builder_local, filename, series, arch):
    artifact = builder_local.Artifact.from_charm(Path(filename))
    series_str, arch_str = map(str, (artifact.series, artifact.arch))
    assert series_str, arch_str == (series, arch)


@pytest.mark.parametrize(
    "risk, expected",
    [
        ("edge", "2.14/edge"),
        ("stable", "0.15/stable"),
        ("candidate", None),
    ],
)
def test_matched_numerical_channel(builder_local, risk, expected):
    track_map = {
        "0.15": ["0.15/edge", "0.15/beta", "0.15/stable"],
        "2.14": ["2.14/edge", "2.14/beta"],
    }
    assert builder_local.matched_numerical_channel(risk, track_map) == expected


def test_build_env_missing_env(builder_local):
    """Ensure missing environment variables raise Exception."""
    with pytest.raises(builder_local.BuildException) as ie:
        builder_local.BuildEnv()
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
def cilib_store(builder_local):
    """Create a fixture defining mock for cilib Store."""
    with patch("builder_local.Store") as store:
        yield store


@pytest.fixture(autouse=True)
def github_repository(builder_local):
    """Create a fixture defining mock for github api."""
    with patch.object(builder_local, "Repository") as repo:
        yield repo.with_session.return_value


@pytest.fixture(autouse=True)
def charm_cmd():
    """Create a fixture defining mock for `charm` cli command."""

    def command_response(cmd, *args, **_kwargs):
        assert cmd == "build"  # this is the only charm command which should be run
        entity_fname, *_ = args
        entity_fname = entity_fname[4:].replace("/", "_")
        fpath = CLI_RESPONSES / f"charm_{cmd}_{entity_fname}.yaml"
        return fpath.read_text() if fpath.exists() else ""

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

    with patch(
        "builder_local._CharmHub.info", side_effect=command_response
    ) as mock_info:
        yield mock_info


@pytest.fixture(autouse=True)
def charmcraft_cmd():
    """Create a fixture defining mock for `charmcraft` cli command."""

    def command_response(*args, **_kwargs):
        fname = "_".join(("charmcraft",) + args)
        fpath = CLI_RESPONSES / f"{fname}.txt"
        return fpath.read_text() if fpath.exists() else ""

    with patch("sh.charmcraft", create=True) as charmcraft:
        cmd = charmcraft.bake.return_value
        cmd.side_effect = command_response
        cmd.status.side_effect = partial(command_response, "status")
        cmd.resources.side_effect = partial(command_response, "resources")
        cmd.revisions.side_effect = partial(command_response, "revisions")
        cmd.pack.side_effect = partial(command_response, "pack")
        yield cmd


@pytest.fixture()
def bundle_environment(test_environment, builder_local):
    charm_env = builder_local.BuildEnv(build_type=builder_local.BuildType.BUNDLE)
    charm_env.db["build_args"] = {
        "job_list": str(CI_TESTING_BUNDLES),
        "branch": "main",
        "filter_by_tag": ["k8s"],
        "to_channel": "edge",
    }
    charm_env.db["pull_layer_manifest"] = []
    yield charm_env


@pytest.fixture()
def charm_environment(test_environment, builder_local):
    charm_env = builder_local.BuildEnv(build_type=builder_local.BuildType.CHARM)
    charm_env.db["build_args"] = {
        "job_list": str(CI_TESTING_CHARMS),
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
        from_channel="latest/edge",
        to_channels=["latest/beta", "1.99/beta"],
        dry_run=False,
    )
    resource_args = [
        "--resource=test-file:994",
        "--resource=test-file-2:993",
    ]
    charmcraft_cmd.release.assert_called_once_with(
        "k8s-ci-charm",
        "--revision=845",
        *resource_args,
        "--channel=latest/beta",
        "--channel=1.99/beta",
    )


@patch("builder_local.os.makedirs", Mock())
@patch("builder_local.git")
def test_build_entity_setup(git, charm_environment, tmpdir, builder_local):
    """Tests build entity setup."""
    artifacts = charm_environment.job_list
    charm_name, charm_opts = next(iter(artifacts[0].items()))
    charm_entity = builder_local.BuildEntity(charm_environment, charm_name, charm_opts)
    assert charm_entity.reactive is False, "Initializes as false"
    charm_entity.setup()
    assert charm_entity.reactive is True, "test charm requires legacy builds"
    git.assert_called_once_with(
        "clone",
        "https://github.com/charmed-kubernetes/jenkins.git",
        charm_entity.checkout_path,
        branch="main",
        _tee=True,
        _out=charm_entity.echo,
    )


def test_build_entity_charm_changes(charm_environment, charm_cmd, builder_local):
    """Tests has_changed property."""
    artifacts = charm_environment.job_list
    charm_name, charm_opts = next(iter(artifacts[0].items()))
    charm_entity = builder_local.BuildEntity(charm_environment, charm_name, charm_opts)
    with patch("builder_local.BuildEntity.commit") as commit:
        # Test non-legacy charms with the commit rev checked in with charm matching
        commit.return_value = "51b893c"
        assert charm_entity.charm_changes is False

        # Test non-legacy charms with the commit rev checked in with charm not matching
        commit.return_value = "51b893d"
        assert charm_entity.charm_changes is True

        # Test legacy charms by comparing charmstore .build.manifest
        charm_entity.reactive = True
        assert charm_entity.charm_changes is True


@patch("builder_local.script")
def test_build_entity_charm_build(
    mock_script, charm_environment, charm_cmd, charmcraft_cmd, tmpdir, builder_local
):
    """Test that BuildEntity runs charm_build."""
    artifacts = charm_environment.job_list
    charm_name, charm_opts = next(iter(artifacts[0].items()))

    charm_entity = builder_local.BuildEntity(charm_environment, charm_name, charm_opts)

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
    charm_entity.artifacts = []
    charm_entity.charm_build()

    manifest_yaml = Path(charm_entity.src_path, "manifest.yaml")
    assert manifest_yaml.exists(), "Manifest not generated"
    manifest_yaml.unlink()

    assert len(charm_entity.artifacts) == 1
    artifact = charm_entity.artifacts[0]
    assert artifact.arch.value == "all"
    assert artifact.arch_docker == "amd64"
    assert artifact.charm_or_bundle == K8S_CI_CHARM / "k8s-ci-charm.charm"
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
    charm_entity.artifacts = []
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
    with pytest.raises(builder_local.BuildException):
        charm_entity.artifacts = []
        charm_entity.charm_build()


def test_build_entity_upload(
    charm_environment, charm_cmd, charmcraft_cmd, tmpdir, builder_local
):
    """Test that BuildEntity pushes to appropriate store."""
    charms = charm_environment.job_list
    charm_name, charm_opts = next(iter(charms[0].items()))

    charmcraft_cmd.upload.return_value = (
        CLI_RESPONSES / "charmcraft_upload_k8s-ci-charm.txt"
    ).read_text()

    charm_entity = builder_local.BuildEntity(charm_environment, charm_name, charm_opts)
    charm_entity.tag = MagicMock()
    artifact = MagicMock()
    charm_entity.push(artifact)
    charm_cmd.push.assert_not_called()
    charmcraft_cmd.upload.assert_called_once_with(artifact.charm_or_bundle)
    charm_entity.tag.assert_called_once_with("k8s-ci-charm-845")
    assert artifact.rev == 845


@pytest.fixture()
def build_entity_tag(charm_environment, builder_local):
    artifacts = charm_environment.job_list
    charm_name, charm_opts = next(iter(artifacts[0].items()))
    charm_entity = builder_local.BuildEntity(charm_environment, charm_name, charm_opts)
    the_tag = f"{charm_entity.name}-369"
    the_sha = "0123456789abcdef0123456789abcdef01234567"

    charm_entity.commit = MagicMock(return_value=the_sha)
    yield the_sha, the_tag, charm_entity


def test_build_entity_tag_dne(build_entity_tag, github_repository):
    the_sha, the_tag, charm_entity = build_entity_tag

    github_repository.get_ref.return_value = {"message": "Not Found"}
    github_repository.tag_commit.return_value = True

    assert charm_entity.tag(the_tag), "Should return tagged=True"
    github_repository.get_ref.assert_called_once_with(tag=the_tag, raise_on_error=False)
    github_repository.create_ref.assert_called_once_with(the_sha, tag=the_tag)


def test_build_entity_tag_duplicate(build_entity_tag, github_repository):
    the_sha, the_tag, charm_entity = build_entity_tag

    charm_entity.commit = MagicMock(return_value=the_sha)
    github_repository.get_ref.return_value = {"object": dict(sha=the_sha)}

    assert charm_entity.tag(the_tag), "Should return tagged=True"
    github_repository.get_ref.assert_called_once_with(tag=the_tag, raise_on_error=False)
    github_repository.tag_commit.assert_not_called()


def test_build_entity_tag_conflict(build_entity_tag, builder_local, github_repository):
    the_sha, the_tag, charm_entity = build_entity_tag

    charm_entity.commit = MagicMock(return_value=the_sha)
    github_repository.get_ref.return_value = {
        "object": dict(sha=the_sha.replace("0", "X"))
    }

    with pytest.raises(builder_local.BuildException):
        charm_entity.tag(the_tag)


@patch("builder_local.os.makedirs", Mock())
def test_build_entity_resource_build(charm_environment, tmpdir, builder_local):
    charms = charm_environment.job_list
    charm_name, charm_opts = next(iter(charms[0].items()))
    charm_entity = builder_local.BuildEntity(charm_environment, charm_name, charm_opts)

    with patch("builder_local.script") as mock_script:
        charm_entity.resource_build()
    mock_script.assert_called_once()


@patch("builder_local.os.makedirs", Mock())
def test_build_entity_assemble_resources(
    charm_environment, charm_cmd, charmcraft_cmd, tmpdir, builder_local
):
    charms = charm_environment.job_list
    charm_name, charm_opts = next(iter(charms[0].items()))
    charm_entity = builder_local.BuildEntity(charm_environment, charm_name, charm_opts)
    artifact = MagicMock()
    artifact.charm_or_bundle = K8S_CI_CHARM
    artifact.resources = []
    charm_entity.assemble_resources(artifact)

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


@pytest.fixture
def ensure_track(builder_local):
    with patch.object(builder_local, "ensure_charm_track") as mocked:
        yield mocked


def test_build_entity_promote(
    charm_environment,
    charm_cmd,
    charmcraft_cmd,
    tmpdir,
    builder_local,
    ensure_track,
):
    """Test that BuildEntity releases to appropriate store."""
    charms = charm_environment.job_list
    charm_name, charm_opts = next(iter(charms[0].items()))

    charm_entity = builder_local.BuildEntity(charm_environment, charm_name, charm_opts)
    artifact = MagicMock()
    artifact.rev = 6
    artifact.resources = [
        builder_local.CharmResource(
            "test-file", kind=builder_local.ResourceKind.FILEPATH, rev=3
        ),
        builder_local.CharmResource(
            "test-image", kind=builder_local.ResourceKind.IMAGE, rev=4
        ),
    ]
    charm_entity.release(artifact, to_channels=("latest/edge", "0.15/edge"))
    charm_cmd.release.assert_not_called()
    ensure_track.assert_has_calls(
        [call("k8s-ci-charm", "latest/edge"), call("k8s-ci-charm", "0.15/edge")]
    )
    ensure_track.reset_mock()
    charmcraft_cmd.release.assert_called_once_with(
        "k8s-ci-charm",
        "--revision=6",
        "--channel=latest/edge",
        "--channel=0.15/edge",
        "--resource=test-file:3",
        "--resource=test-image:4",
    )
    charmcraft_cmd.release.reset_mock()

    charm_entity.release(artifact, to_channels=("latest/stable", "0.15/stable"))
    charm_cmd.release.assert_not_called()
    ensure_track.assert_has_calls(
        [call("k8s-ci-charm", "latest/stable"), call("k8s-ci-charm", "0.15/stable")]
    )
    ensure_track.reset_mock()
    charmcraft_cmd.release.assert_called_once_with(
        "k8s-ci-charm",
        "--revision=6",
        "--channel=latest/stable",
        "--channel=0.15/stable",
        "--resource=test-file:3",
        "--resource=test-image:4",
    )
    charmcraft_cmd.release.reset_mock()

    charm_entity.release(artifact, to_channels=("0.14/stable",))
    charm_cmd.release.assert_not_called()
    ensure_track.assert_called_once_with("k8s-ci-charm", "0.14/stable")
    charmcraft_cmd.release.assert_called_once_with(
        "k8s-ci-charm",
        "--revision=6",
        "--channel=0.14/stable",
        "--resource=test-file:3",
        "--resource=test-image:4",
    )
    charmcraft_cmd.release.reset_mock()


def test_bundle_build_entity_push(
    bundle_environment, charm_cmd, charmcraft_cmd, tmpdir, builder_local
):
    """Test that BundleBuildEntity pushes to appropriate store."""
    bundles = bundle_environment.job_list
    bundle_name, bundle_opts = next(iter(bundles[0].items()))

    bundle_opts["src_path"] = bundle_environment.default_repo_dir
    bundle_opts["dst_path"] = bundle_environment.bundles_dir / bundle_name
    charmcraft_cmd.upload.return_value = (
        CLI_RESPONSES / "charmcraft_upload_test-kubernetes.txt"
    ).read_text()
    bundle_entity = builder_local.BundleBuildEntity(
        bundle_environment, bundle_name, bundle_opts
    )
    artifact = MagicMock()
    bundle_entity.tag = MagicMock()
    bundle_entity.push(artifact)
    charm_cmd.push.assert_not_called()
    charmcraft_cmd.upload.assert_called_once_with(artifact.charm_or_bundle)
    bundle_entity.tag.assert_called_once_with("test-kubernetes-123")
    assert artifact.rev == 123


@patch("builder_local.sh.Command")
def test_bundle_build_entity_bundle_build(
    sh_cmd, charmcraft_cmd, bundle_environment, builder_local
):
    """Tests bundle_build method."""
    bundles = bundle_environment.job_list
    bundle_name, bundle_opts = next(iter(bundles[0].items()))
    bundle_opts["src_path"] = K8S_CI_BUNDLE
    bundle_opts["dst_path"] = dst_path = bundle_environment.bundles_dir / bundle_name

    # Test a bundle copy takes place
    # Test that a bundle pack occurs
    bundle_opts["skip-build"] = True
    bundle_entity = builder_local.BundleBuildEntity(
        bundle_environment, bundle_name, bundle_opts
    )
    bundle_entity.bundle_build("edge")
    charmcraft_cmd.pack.assert_called_once_with(_cwd=dst_path)
    assert len(bundle_entity.artifacts) == 1
    artifact = bundle_entity.artifacts[0]
    assert artifact.charm_or_bundle == Path(
        "/not/real/path/to/scratch/tmp/bundles/test-kubernetes.zip"
    )
    assert (dst_path / "bundle.yaml").exists()
    assert (dst_path / "tests" / "test.yaml").exists()
    sh_cmd.assert_not_called()
    bundle_entity.reset_artifacts()
    dst_path.mkdir()

    # Test a bundle build takes place
    del bundle_opts["skip-build"]
    bundle_entity = builder_local.BundleBuildEntity(
        bundle_environment, bundle_name, bundle_opts
    )
    bundle_entity.bundle_build("edge")
    assert not (dst_path / "bundle.yaml").exists()
    sh_cmd.assert_called_with(f"{K8S_CI_BUNDLE}/bundle")
    sh_cmd.return_value.assert_called_with(
        "-n",
        "test-kubernetes",
        "-o",
        str(dst_path),
        "-c",
        "edge",
        "k8s/core",
        "cni/flannel",
        "cri/containerd",
        _tee=True,
        _out=bundle_entity.echo,
    )
    sh_cmd.reset_mock()
    shutil.rmtree(dst_path)


def test_bundle_build_entity_differs(bundle_environment, charm_cmd, builder_local):
    """Tests has_changed property."""
    bundles = bundle_environment.job_list
    bundle_name, bundle_opts = next(iter(bundles[0].items()))
    bundle_opts["src_path"] = bundle_environment.default_repo_dir

    # Test all charmhub charms comparing .build.manifest to revision
    bundle_entity = builder_local.BundleBuildEntity(
        bundle_environment, bundle_name, bundle_opts
    )
    artifact = MagicMock()
    artifact.charm_or_bundle = K8S_CI_BUNDLE.with_suffix(".bundle")
    with patch.object(
        bundle_entity, "download", return_value=MagicMock(autospec=ZipFile)
    ):
        assert bundle_entity.bundle_differs(artifact) is True


#   --------------------------------------------------
#  test click command functions


@pytest.fixture()
def mock_build_env():
    """Create a fixture defining a mock BuildEnv object."""
    with patch("main.BuildEnv") as mock_env:
        mock_env_inst = mock_env.return_value
        mock_env_inst.db = {}
        yield mock_env_inst


@pytest.fixture()
def mock_build_entity():
    """Create a fixture defining a mock BuildEntity object."""
    with patch("main.BuildEntity") as mock_ent:
        yield mock_ent


@pytest.fixture()
def mock_bundle_build_entity(main):
    """Create a fixture defining a mock BundleBuildEntity object."""
    spec = dir(main.BundleBuildEntity)
    with patch("main.BundleBuildEntity") as mock_ent:

        def create_mock_bundle(*args):
            mm = MagicMock(spec=spec)
            mm.build, mm.name, mm.opts = args
            mm.artifacts = [MagicMock()]
            mock_ent.entities.append(mm)
            return mm

        mock_ent.side_effect = create_mock_bundle
        mock_ent.entities = []
        yield mock_ent


def test_promote_command(mock_build_env, main):
    """Tests cli promote command which is run by jenkins job."""
    runner = CliRunner()
    result = runner.invoke(
        main.promote,
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
        "job_list": "test-charm",
        "filter_by_tag": ["tag1", "tag2"],
        "from_channel": "latest/edge",
        "to_channel": "latest/beta",
        "track": "latest",
    }
    mock_build_env.promote_all.assert_called_once_with(
        from_channel="latest/edge",
        to_channels=mock_build_env.to_channels,
        dry_run=False,
    )


@patch("builder_local.sh", MagicMock())
def test_build_command(mock_build_env, mock_build_entity, main):
    """Tests cli build command which is run by jenkins job."""
    runner = CliRunner()
    mock_build_env.job_list = [
        {
            "k8s-ci-charm": dict(
                tags=["tag1", "k8s"],
                namespace="containers",
                downstream="charmed-kubernetes/layer-k8s-ci-charm.git",
            ),
            "ignored": dict(tags=["ignore-me"]),
        }
    ]
    mock_build_env.track = "latest"
    mock_build_env.filter_by_tag = ["tag1", "tag2"]
    mock_build_env.to_channels = ["edge", "1.18/edge"]
    artifact = MagicMock()
    entity = mock_build_entity.return_value
    entity.artifacts = [artifact]
    result = runner.invoke(
        main.build,
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
        "job_list": "tests/data/ci-testing-charms.inc",
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
    entity.push.assert_called_once_with(artifact)
    entity.assemble_resources.assert_called_once_with(
        artifact, to_channels=["latest/edge", "1.18/edge"]
    )
    entity.release.assert_called_once_with(
        artifact, to_channels=["latest/edge", "1.18/edge"]
    )


@patch("main.git")
def test_bundle_build_command(
    git, mock_build_env, mock_bundle_build_entity, tmpdir, main
):
    """Tests cli build command which is run by jenkins job."""
    runner = CliRunner()
    mock_build_env.job_list = [
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
    mock_build_env.track = "latest"
    mock_build_env.filter_by_tag = ["k8s"]
    mock_build_env.force = False

    result = runner.invoke(
        main.build_bundles,
        [
            "--bundle-list=tests/data/ci-testing-bundles.inc",
            "--filter-by-tag=k8s",
        ],
    )
    if result.exception:
        raise result.exception

    assert mock_build_env.db["build_args"] == {
        "job_list": "tests/data/ci-testing-bundles.inc",
        "branch": "main",
        "filter_by_tag": mock_build_env.filter_by_tag,
        "track": "latest",
        "to_channel": "edge",
        "force": False,
    }
    git.assert_called_once_with(
        "clone",
        "https://github.com/charmed-kubernetes/bundle.git",
        mock_build_env.default_repo_dir,
        branch="main",
    )
    mock_build_env.pull_layers.assert_not_called()
    mock_build_env.save.assert_called_once_with()

    for entity in mock_bundle_build_entity.entities:
        artifact = entity.artifacts[0]
        entity.echo.assert_has_calls(
            [
                call("Starting"),
                call(f"Details: {entity}"),
                call("Pushing built bundle for channel=latest/edge (forced=False)."),
                call("Pushing built bundle for channel=0.15/edge (forced=False)."),
                call("Stopping"),
            ],
            any_order=False,
        )
        if "downstream" in entity.opts:
            entity.setup.assert_called_once_with()

        assert entity.bundle_build.mock_calls == [
            call(channel) for channel in ["latest/edge", "0.15/edge"]
        ]
        assert entity.push.mock_calls == [call(artifact), call(artifact)]
        assert entity.release.mock_calls == [
            call(artifact, to_channels=[channel])
            for channel in ["latest/edge", "0.15/edge"]
        ]
        assert entity.reset_artifacts.mock_calls == [call(), call()]
