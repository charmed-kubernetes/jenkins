from cilib.models.repos.snaps import SnapKubeletRepoModel


def test_repo_matches_model():
    """Test that repo model matches the upstream repo"""
    repo_model = SnapKubeletRepoModel()
    assert repo_model.repo == "git+ssh://k8s-team-ci@git.launchpad.net/snap-kubelet"


def test_get_proper_tracks():
    """Test that proper tracks are associated with known versions"""
    repo_model = SnapKubeletRepoModel()
    assert repo_model.tracks("1.34") == [
        "1.34/stable",
        "1.34/candidate",
        "1.34/beta",
        "1.34/edge",
    ]
