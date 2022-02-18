import tempfile
import semver
from subprocess import run
from cilib.models.repos.kubernetes import (
    BaseRepoModel,
    UpstreamKubernetesRepoModel,
    InternalKubernetesRepoModel,
)
from cilib.models.repos.snaps import SnapKubeletRepoModel


def test_tags_semver_point(monkeypatch):
    """Test getting tags from a starting semver"""
    monkeypatch.setattr(
        "cilib.models.repos.kubernetes.InternalKubernetesRepoModel.tags",
        ["v1.16.1", "v1.17.1", "v1.17.2", "v1.18.1"],
    )
    DOWNSTREAM = InternalKubernetesRepoModel()
    tags = DOWNSTREAM.tags_from_semver_point("v1.17.0")
    assert tags == ["v1.17.1", "v1.17.2", "v1.18.1"]


def test_tags_subset_semver_point(monkeypatch):
    """Test getting subset of tags from a starting semver"""
    monkeypatch.setattr(
        "cilib.models.repos.kubernetes.UpstreamKubernetesRepoModel.tags",
        ["v1.17.5", "v1.17.6", "v1.17.7"],
    )
    monkeypatch.setattr(
        "cilib.models.repos.kubernetes.InternalKubernetesRepoModel.tags",
        ["v1.17.0", "v1.17.1", "v1.17.2"],
    )
    ustream = UpstreamKubernetesRepoModel()
    dstream = InternalKubernetesRepoModel()
    tags = ustream.tags_subset_semver_point(dstream, "v1.17.0")
    assert "v1.16.0" not in tags
    assert "v1.17.5" in tags


def test_add_remote_repo():
    """Test that creating a remote repo works"""
    base_repo = BaseRepoModel()
    with tempfile.TemporaryDirectory() as tmpdir:
        run("git init .", shell=True, cwd=tmpdir)
        base_repo.remote_add("downstream", "https://example.com/repo.git", cwd=tmpdir)
        remote_repos = run("git remote -v", shell=True, cwd=tmpdir, capture_output=True)
        assert "downstream" in remote_repos.stdout.decode()
        assert "https://example.com/repo.git" in remote_repos.stdout.decode()


def test_latest_branch_from_major_minor(monkeypatch):
    """Test getting latest branch version from a major.minor release"""

    monkeypatch.setattr(
        "cilib.models.repos.snaps.BaseRepoModel.branches",
        ["v1.19.0", "v1.19.1", "v1.19.3"],
    )
    kubelet_repo = SnapKubeletRepoModel()
    max_branch = kubelet_repo.base.latest_branch_from_major_minor("1.19")
    assert semver.VersionInfo.parse(max_branch).compare("1.19.3") == 0


def test_latest_patched_branch_from_major_minor(monkeypatch):
    """Test getting latest branch with a patch applied from a major.minor release"""

    monkeypatch.setattr(
        "cilib.models.repos.snaps.BaseRepoModel.branches",
        [
            "v1.19.0",
            "v1.19.1+patch.2",
            "v1.19.3",
            "v1.19.3+patch.1",
            "v1.19.3+patch.4",
            "v1.19.3+patch.12",
        ],
    )
    kubelet_repo = SnapKubeletRepoModel()
    max_branch = kubelet_repo.base.latest_branch_from_major_minor("1.19")
    assert semver.VersionInfo.parse(max_branch).compare("1.19.3+patch.12") == 0
