from cilib.models.repos.snaps import SnapKubeletRepoModel
import semver

revision_output = """Rev.    Uploaded              Arch    Version               Channels
1629    2020-10-20T14:27:17Z  amd64   1.19.3                1.19/stable*, 1.19/candidate*, 1.19/beta*, 1.19/edge*
1627    2020-10-20T14:24:15Z  amd64   1.20.0-alpha.3        1.20/edge*
1626    2020-10-20T14:22:44Z  amd64   1.18.10               1.18/stable*, 1.18/candidate*, 1.18/beta*, 1.18/edge*
1620    2020-10-20T14:12:17Z  amd64   1.17.13               1.17/stable*, 1.17/candidate*, 1.17/beta*, 1.17/edge*
1618    2020-10-20T14:07:17Z  amd64   1.16.15               1.16/stable*, 1.16/candidate*, 1.16/beta*, 1.16/edge*
1615    2020-09-30T20:53:21Z  amd64   1.19.2                1.19/candidate, 1.19/beta, 1.19/edge, stable*, beta*, candidate*, edge*, 1.19/stable
1610    2020-09-30T19:34:14Z  amd64   1.19.0                1.19/stable, 1.19/candidate, 1.19/beta, 1.19/edge, edge, beta, candidate, stable
1609    2020-09-29T18:41:31Z  amd64   1.17.12               1.17/stable, 1.17/candidate, 1.17/beta, 1.17/edge
1608    2020-09-29T18:41:18Z  amd64   1.16.15               1.16/stable, 1.16/candidate, 1.16/beta, 1.16/edge
1607    2020-09-29T18:39:14Z  amd64   1.18.9                1.18/stable, 1.18/candidate, 1.18/beta, 1.18/edge
1604    2020-08-27T14:40:21Z  amd64   1.19.0                1.19/stable, 1.19/candidate, 1.19/beta, 1.19/edge
1597    2020-08-26T21:06:13Z  amd64   1.16.14               1.16/stable, 1.16/candidate, 1.16/beta, 1.16/edge
1595    2020-08-26T21:00:33Z  amd64   1.18.8                1.18/stable, 1.18/candidate, 1.18/beta, 1.18/edge, stable, candidate, beta, edge
1592    2020-08-26T20:42:15Z  amd64   1.17.11               1.17/stable, 1.17/candidate, 1.17/beta, 1.17/edge
1587    2020-08-13T13:59:27Z  amd64   1.17.10               1.17/stable, 1.17/candidate, 1.17/beta, 1.17/edge
1585    2020-08-13T13:51:17Z  amd64   1.18.7                1.18/candidate, 1.18/beta, 1.18/edge
1579    2020-08-05T13:41:20Z  amd64   1.19.0-rc.4           1.19/candidate, 1.19/beta, 1.19/edge
1575    2020-07-29T14:51:15Z  amd64   1.19.0-rc.3           1.19/candidate, 1.19/beta, 1.19/edge
1572    2020-07-21T14:15:30Z  amd64   1.19.0-rc.1           1.19/candidate, 1.19/beta, 1.19/edge
1570    2020-07-16T17:27:25Z  amd64   1.17.9                1.17/stable, 1.17/candidate, 1.17/beta, 1.17/edge
1564    2020-07-16T14:29:22Z  amd64   1.16.13               1.16/stable, 1.16/candidate, 1.16/beta, 1.16/edge
1560    2020-07-16T14:23:15Z  amd64   1.18.6                1.18/stable, 1.18/candidate, 1.18/beta, 1.18/edge, stable, beta, candidate, edge
1558    2020-07-15T15:11:20Z  amd64   1.19.0-rc.1           1.19/candidate, 1.19/beta, 1.19/edge
1552    2020-07-14T13:46:14Z  amd64   1.19.0-rc.0           1.19/candidate, 1.19/beta, 1.19/edge
1549    2020-07-10T17:21:22Z  amd64   1.19.0-rc.0           1.19/candidate, 1.19/beta, 1.19/edge
"""


def mock_get_revision_output(*args, **kwargs):
    return revision_output.splitlines()[1:]


def test_repo_matches_model():
    """Test that repo model matches the upstream repo"""
    repo_model = SnapKubeletRepoModel()
    assert repo_model.repo == "git+ssh://k8s-team-ci@git.launchpad.net/snap-kubelet"


def test_get_revisions(monkeypatch):
    """Test that revisions are being mapped properly"""
    monkeypatch.setattr(
        SnapKubeletRepoModel, "_get_revision_output", mock_get_revision_output
    )
    repo_model = SnapKubeletRepoModel()
    revisions = repo_model.revisions()
    assert revisions["1609"]["string_version"] == "1.17.12"
    assert semver.compare(revisions["1629"]["string_version"], "1.19.3") == 0


def test_rev_1618_promoted(monkeypatch):
    """Test that rev 1618 is promoted in all channels"""
    monkeypatch.setattr(
        SnapKubeletRepoModel, "_get_revision_output", mock_get_revision_output
    )
    repo_model = SnapKubeletRepoModel()
    revisions = repo_model.revisions()
    channels = revisions["1618"]["channels"]
    assert all([channel["promoted"] is True for channel in channels]) == True


def test_get_latest_revision(monkeypatch):
    """Test that the latest revision is found for 1.19"""
    monkeypatch.setattr(
        SnapKubeletRepoModel, "_get_revision_output", mock_get_revision_output
    )
    repo_model = SnapKubeletRepoModel()
    assert repo_model.latest_revision("1.19/stable") == "1629"


def test_get_proper_tracks():
    """Test that proper tracks are associated with known versions"""
    repo_model = SnapKubeletRepoModel()
    repo_model.version = "1.19"
    assert repo_model.tracks == [
        "1.19/stable",
        "1.19/candidate",
        "1.19/beta",
        "1.19/edge",
    ]
    repo_model.version = "1.20"
    assert repo_model.tracks == ["1.20/edge"]
