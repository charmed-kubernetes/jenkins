from cilib.models.repos.snaps import SnapKubeletRepoModel
import semver


def test_repo_matches_model():
    """Test that repo model matches the upstream repo"""
    repo_model = SnapKubeletRepoModel()
    assert repo_model.repo == "git+ssh://k8s-team-ci@git.launchpad.net/snap-kubelet"


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
