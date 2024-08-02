import base64
import logging
import json
import os
import subprocess
import re
import urllib.request

from typing import Optional

log = logging.getLogger(__name__)


def _charmcraft_auth_to_macaroon(charmcraft_auth: str) -> Optional[str]:
    """Decode charmcraft auth into the macaroon."""
    try:
        bytes = base64.b64decode(charmcraft_auth.strip().encode())
        return json.loads(bytes).get("v")
    except (base64.binascii.Error, json.JSONDecodeError):
        return None


def _track_or_channel(channel: str):
    """Get the track from a channel."""
    return channel.split("/")[0] if "/" in channel else channel


def macaroon():
    """Get the charmhub macaroon."""
    macaroon = os.getenv("CHARM_MACAROON", "")
    if not macaroon and (charmcraft_auth := os.getenv("CHARMCRAFT_AUTH")):
        macaroon = _charmcraft_auth_to_macaroon(charmcraft_auth)
    if not macaroon:
        out = subprocess.run(
            ["charmcraft", "login", "--export", "/dev/fd/2"],
            stderr=subprocess.PIPE,
            text=True,
            check=True,
        )
        macaroon = _charmcraft_auth_to_macaroon(out.stderr.splitlines()[-1])
    if not macaroon:
        raise ValueError("No charmhub macaroon found")
    os.environ["CHARM_MACAROON"] = macaroon
    return macaroon


def request(url: str):
    """Create a request with the appropriate macaroon."""
    return urllib.request.Request(
        url,
        method="GET",
        headers={
            "Authorization": f"Macaroon {macaroon()}",
            "Content-Type": "application/json",
        },
    )


def info(charm: str):
    """Get charm info."""
    req = request(f"https://api.charmhub.io/v1/charm/{charm}")
    with urllib.request.urlopen(req) as resp:
        if 200 <= resp.status < 300:
            log.debug(f"Got charm info for {charm}")
            return json.loads(resp.read())
    raise ValueError(f"Failed to get charm info for {charm}: {resp.status}")


def create_track(charm: str, track_or_channel: str):
    """Create a track for a charm."""
    req = request(f"https://api.charmhub.io/v1/charm/{charm}/tracks")
    req.method = "POST"
    track = _track_or_channel(track_or_channel)
    req.data = json.dumps([{"name": track}]).encode()
    with urllib.request.urlopen(req) as resp:
        if 200 <= resp.status < 300:
            log.info(f"Track {track} created for charm {charm}")
            return
    raise ValueError(f"Failed to create track {track} for charm {charm}: {resp.read()}")


def ensure_track(charm: str, track_or_channel: str):
    """Ensure a track exists for a charm."""
    charm_info = info(charm)
    track = _track_or_channel(track_or_channel)
    charm_tracks = [t["name"] for t in charm_info["metadata"]["tracks"]]
    if track in charm_tracks:
        log.info(f"Track {track} already exists for charm {charm}")
        return
    patterns = [t["pattern"] for t in charm_info["metadata"]["track-guardrails"]]
    if not any(re.compile(f"^{pattern}$").match(track) for pattern in patterns):
        raise ValueError(
            f"Track {track} does not match any guardrails for charm {charm}"
        )

    return create_track(charm, track)
