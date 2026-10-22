import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
SYNC_SCRIPT = ROOT / "jobs/sync-oci-images/sync-oci-images.sh"


def run_sync_fn(tmp_path, body):
    return subprocess.run(
        ["bash", "-c", f'source "{SYNC_SCRIPT}"\n{body}'],
        cwd=tmp_path,
        text=True,
        capture_output=True,
    )


def test_set_image_line_appends_on_own_line_when_file_lacks_trailing_newline(tmp_path):
    images = tmp_path / "container-images.txt"
    images.write_text("v1.36-static: registry.k8s.io/pause:3.9")

    completed = run_sync_fn(
        tmp_path,
        "set_image_line container-images.txt 'v1.36.5-upstream: docker.io/coredns/coredns:1.9.4'",
    )

    assert completed.returncode == 0, completed.stderr
    assert images.read_text() == (
        "v1.36-static: registry.k8s.io/pause:3.9\n"
        "v1.36.5-upstream: docker.io/coredns/coredns:1.9.4\n"
    )


def test_set_image_line_replaces_existing_key_without_duplicating(tmp_path):
    images = tmp_path / "container-images.txt"
    images.write_text(
        "v1.36-static: registry.k8s.io/pause:3.9\n"
        "v1.36.5-upstream: docker.io/coredns/coredns:1.9.3\n"
    )

    completed = run_sync_fn(
        tmp_path,
        "set_image_line container-images.txt 'v1.36.5-upstream: docker.io/coredns/coredns:1.9.4'",
    )

    assert completed.returncode == 0, completed.stderr
    assert images.read_text() == (
        "v1.36-static: registry.k8s.io/pause:3.9\n"
        "v1.36.5-upstream: docker.io/coredns/coredns:1.9.4\n"
    )


@pytest.mark.parametrize(
    ("image", "expected"),
    [
        ("docker.io/library/busybox:1.32", "ghcr.io/canonical/cdk/busybox:1.32"),
        ("docker.io/calico/node:v3.29.3", "ghcr.io/canonical/cdk/calico/node:v3.29.3"),
        ("k8s.gcr.io/pause:3.2", "ghcr.io/canonical/cdk/pause:3.2"),
        ("registry.k8s.io/dns/k8s-dns-sidecar:1.26.7", "ghcr.io/canonical/cdk/dns/k8s-dns-sidecar:1.26.7"),
        ("rocks.canonical.com/cdk/addon-resizer-amd64:1.8.9", "ghcr.io/canonical/cdk/addon-resizer-amd64:1.8.9"),
    ],
)
def test_published_ref_maps_source_to_ghcr_path(tmp_path, image, expected):
    completed = run_sync_fn(tmp_path, f"published_ref '{image}'")

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == expected


def test_published_ref_rejects_unknown_registry(tmp_path):
    completed = run_sync_fn(tmp_path, "published_ref 'mcr.microsoft.com/foo:1.0'")

    assert completed.returncode != 0
    assert "no target mapping" in completed.stderr
