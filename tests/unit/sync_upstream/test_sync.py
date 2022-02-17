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
            mock.call("juju-solutions/interface-aws-iam"),
            mock.call("charmed-kubernetes/interface-aws-iam"),
        ],
        any_order=False,
    )
    for (name, args, kwargs) in mock_base().mock_calls:
        assert name in ["clone", "remote_add", "fetch", "checkout", "merge", "push"]
        if ref := kwargs.get("ref"):
            assert ref == "test-main"


@mock.patch("sync.CharmRepoModel.base", new_callable=mock.PropertyMock)
@mock.patch("sync.default_gh_branch", return_value=None)
def test_sync_no_default_branch(mock_default_gh, mock_base, sync):
    """Tests the repo default branch helper which runs when syncing forks."""
    result = sync.CharmRepoModel.default_gh_branch(mock_base, remote="test-repo")
    assert result == "master"
