from types import SimpleNamespace

import pytest

from cilib.snapapi import SnapStore


def test_channel_map_reports_surl_failure(monkeypatch):
    """Surface the Store API error instead of attempting to decode empty output."""
    monkeypatch.setattr(
        "cilib.snapapi.capture",
        lambda _command: SimpleNamespace(
            ok=False,
            returncode=1,
            stdout=b"",
            stderr=b"authentication expired",
        ),
    )

    with pytest.raises(
        RuntimeError,
        match="surl_cli.py exited 1: authentication expired",
    ):
        SnapStore("kube-apiserver").channel_map
