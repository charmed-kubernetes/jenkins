import tempfile
import semver
from subprocess import run
from cilib.models.repos.kubernetes import (
    BaseRepoModel,
    UpstreamKubernetesRepoModel,
    InternalKubernetesRepoModel,
)
from cilib.models.repos.snaps import SnapKubeletRepoModel

UPSTREAM = UpstreamKubernetesRepoModel()
DOWNSTREAM = InternalKubernetesRepoModel()


def test_tags_semver_point():
    """Test getting tags from a starting semver"""
    tags = DOWNSTREAM.tags_from_semver_point("v1.19.0")
    assert len(tags) > 0


def test_tags_subset_semver_point():
    """Test getting subset of tags from a starting semver"""
    tags = UPSTREAM.tags_subset_semver_point(DOWNSTREAM, "v1.17.0")
    assert "v1.17.0" in tags
    assert "v1.17.1" in tags


def test_add_remote_repo():
    """Test that creating a remote repo works"""
    base_repo = BaseRepoModel()
    with tempfile.TemporaryDirectory() as tmpdir:
        run("git init .", shell=True, cwd=tmpdir)
        base_repo.remote_add("downstream", "https://example.com/repo.git", cwd=tmpdir)
        remote_repos = run("git remote -v", shell=True, cwd=tmpdir, capture_output=True)
        assert "downstream" in remote_repos.stdout.decode()
        assert "https://example.com/repo.git" in remote_repos.stdout.decode()


def test_latest_branch_from_major_minor():
    """Test getting latest branch version from a major.minor release"""
    kubelet_repo = SnapKubeletRepoModel()
    max_branch = kubelet_repo.latest_branch_from_major_minor("1.14")
    assert semver.compare(max_branch, "1.14.10") == 0
