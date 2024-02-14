from unittest import mock

from click.testing import CliRunner


@mock.patch("sync.CharmRepoModel.base", new_callable=mock.PropertyMock)
@mock.patch("sync.CharmRepoModel.default_gh_branch", return_value="test-main")
def test_sync_default_branch(mock_default_gh, mock_base, sync):
    """Tests cli forks command which is run by jenkins job."""
    runner = CliRunner()
    result = runner.invoke(
        sync.forks,
        [
            "--dry-run",
        ],
    )
    assert result.exception is None
    mock_default_gh.assert_has_calls(
        [
            mock.call("juju-solutions/interface-aws-integration"),
            mock.call("charmed-kubernetes/interface-aws-integration"),
        ],
        any_order=False,
    )
    for name, args, kwargs in mock_base().mock_calls:
        assert name in ["clone", "remote_add", "fetch", "checkout", "merge", "push"]
        if ref := kwargs.get("ref"):
            assert ref == "test-main"


@mock.patch("sync.CharmRepoModel.base", new_callable=mock.PropertyMock)
@mock.patch("cilib.git.default_gh_branch", mock.MagicMock(return_value=None))
def test_sync_no_default_branch(mock_base, sync):
    """Tests the repo default branch helper which runs when syncing forks."""
    mock_base.git_user, mock_base.password = "git-user", "git-password"
    result = sync.CharmRepoModel.default_gh_branch(mock_base, remote="test/repo")
    assert result == "master"


@mock.patch("sync.Repository.default_branch", mock.PropertyMock(return_value="main"))
@mock.patch("sync.Repository.branches", mock.PropertyMock(return_value=["main"]))
@mock.patch("sync.Repository.copy_branch")
def test_sync_cut_stable_release(mock_copy_branch, sync):
    """Tests that cut stable release job creates a new branch from the default branch."""
    runner = CliRunner()
    with mock.patch.object(sync, "SNAP_K8S_TRACK_LIST", [("100.23", None)]):
        result = runner.invoke(
            sync.cut_stable_release,
            [
                "--dry-run",
                "--layer-list=jobs/includes/charm-layer-list.inc",
                "--charm-list=jobs/includes/charm-support-matrix.inc",
                "--ancillary-list=jobs/includes/ancillary-list.inc",
                "--filter-by-tag=calico",
            ],
        )
    assert result.exception is None
    mock_copy_branch.assert_called_once_with("main", "release_100.23")


@mock.patch("sync.Repository.default_branch", mock.PropertyMock(return_value="main"))
@mock.patch("sync.Repository.tags", mock.PropertyMock(return_value=[]))
@mock.patch("sync.Repository.tag_branch")
def test_tag_stable_bundle(mock_tag_branch, sync):
    """Tests that tag stable bundle job creates a tags selected branch with release."""
    runner = CliRunner()
    with mock.patch.object(sync, "SNAP_K8S_TRACK_LIST", [("100.23", None)]):
        result = runner.invoke(
            sync.tag_stable,
            [
                "--layer-list=jobs/includes/charm-layer-list.inc",
                "--charm-list=jobs/includes/charm-support-matrix.inc",
                "--k8s-version=100.23",
                "--bundle-revision=1234",
                "--dry-run",
                "--filter-by-tag=calico",
            ],
        )
    assert result.exception is None
    mock_tag_branch.assert_called_once_with("release_100.23", "ck-100.23-1234")


@mock.patch("sync.Repository.default_branch", mock.PropertyMock(return_value="main"))
@mock.patch("sync.Repository.tags", mock.PropertyMock(return_value=["ck-100.23-1234"]))
@mock.patch("sync.Repository.tag_branch")
def test_tag_stable_bugfix(mock_tag_branch, sync):
    """Tests that tag stable bundle job creates a tags selected branch with release."""
    runner = CliRunner()
    with mock.patch.object(sync, "SNAP_K8S_TRACK_LIST", [("100.23", None)]):
        result = runner.invoke(
            sync.tag_stable,
            [
                "--layer-list=jobs/includes/charm-layer-list.inc",
                "--charm-list=jobs/includes/charm-support-matrix.inc",
                "--k8s-version=100.23",
                "--bundle-revision=ck2",
                "--dry-run",
                "--bugfix",
                "--filter-by-tag=calico",
            ],
        )
    assert result.exception is None
    mock_tag_branch.assert_called_once_with("release_100.23", "100.23+ck2")


@mock.patch(
    "sync.Repository.branches",
    mock.PropertyMock(return_value=["main", "release_100.23"]),
)
@mock.patch("sync.Repository.rename_branch")
def test_rename_branch(mock_rename_branch, sync):
    """Tests that tag stable bundle job creates a tags selected branch with release."""
    runner = CliRunner()
    with mock.patch.object(sync, "SNAP_K8S_TRACK_LIST", [("100.23", None)]):
        result = runner.invoke(
            sync.rename_branch,
            [
                "--layer-list=jobs/includes/charm-layer-list.inc",
                "--charm-list=jobs/includes/charm-support-matrix.inc",
                "--ancillary-list=jobs/includes/ancillary-list.inc",
                "--from-name=release_100.23",
                "--to-name=release-100.23",
                "--dry-run",
                "--filter-by-tag=calico",
            ],
        )
    assert result.exception is None
    mock_rename_branch.assert_called_once_with("release_100.23", "release-100.23")
