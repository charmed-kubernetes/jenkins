#!/usr/bin/env python3

import argparse
import base64
import logging
import json
import os
import subprocess
import sys
import re
import urllib.request

from typing import Optional


def _base64_json(creds: str) -> Optional[str]:
    """Decode charmcraft auth into the macaroon."""
    try:
        bytes = base64.b64decode(creds.strip().encode())
        return json.loads(bytes).get("v")
    except (base64.binascii.Error, json.JSONDecodeError, UnicodeDecodeError) as e:
        log.warning("Failed to decode base64 json: %s", e)
        return None


def _request(url: str, authorization: str = None):
    """Create a request with the appropriate macaroon."""
    return urllib.request.Request(
        url,
        method="GET",
        headers={
            "Authorization": authorization,
            "Accept": "application/json",
            "Content-Type": "application/json",
        },
    )


def _track_or_channel(channel: str):
    """Get the track from a channel."""
    return channel.split("/")[0] if "/" in channel else channel


def _save_auth_header(auth_header: str) -> str:
    """Save the macaroon for later use."""
    os.environ["CH_AUTH_HEADER"] = auth_header
    return auth_header


def _load_auth_header() -> Optional[str]:
    """Load the macaroon from the environment."""
    return os.getenv("CH_AUTH_HEADER", None)


def charmhub_auth_header():
    """Get the authentication macaroon."""
    if macaroon := _load_auth_header():
        log.debug("Reusing existing auth header")
        return macaroon
    if charmcraft_auth := os.getenv("CHARMCRAFT_AUTH"):
        log.debug("Trying to use env CHARMCRAFT_AUTH to get macaroon...")
        macaroon = _base64_json(charmcraft_auth)
    if not macaroon:
        log.debug("Trying to use 'charmcraft login' to get macaroon...")
        out = subprocess.run(
            ["charmcraft", "login", "--export", "/dev/fd/2"],
            stderr=subprocess.PIPE,
            text=True,
            check=True,
        )
        macaroon = _base64_json(out.stderr.splitlines()[-1])
    if not macaroon:
        log.error("Cannot load charmcraft macaroon")
        raise ValueError("No macaroon found -- Cannot authenticate")
    if not isinstance(macaroon, str):
        log.error("Macaroon wasn't a str")
        raise ValueError("Invalid macaroon found -- Cannot authenticate")
    return _save_auth_header(f"Macaroon {macaroon}")


def info(kind: str, name: str):
    """Get entity info."""
    req = _request(f"https://api.charmhub.io/v1/{kind}/{name}", charmhub_auth_header())
    with urllib.request.urlopen(req) as resp:
        log.debug("Received info for %s '%s'", kind, name)
        return json.loads(resp.read())


def create_track(kind: str, name: str, track_or_channel: str):
    """Create a track for an entity."""
    req = _request(
        f"https://api.charmhub.io/v1/{kind}/{name}/tracks", charmhub_auth_header()
    )
    req.method = "POST"
    track = _track_or_channel(track_or_channel)
    req.data = json.dumps([{"name": track}]).encode()
    with urllib.request.urlopen(req):
        log.info("Track %-10s created for %5s %s", track, kind, name)
        return


def ensure_track(kind: str, name: str, track_or_channel: str):
    """Ensure a track exists for a named entity."""
    entity_info = info(kind, name)
    track = _track_or_channel(track_or_channel)
    tracks = [t["name"] for t in entity_info["metadata"]["tracks"]]
    if track in tracks:
        log.info("Track %-10s exists for %5s %s", track, kind, name)
        return
    patterns = [t["pattern"] for t in entity_info["metadata"]["track-guardrails"]]
    if not any(re.compile(f"^{pattern}$").match(track) for pattern in patterns):
        raise ValueError(
            f"Track {track} does not match any guardrails for {kind} {name}"
        )
    return create_track(kind, name, track)


def ensure_charm_track(charm: str, track: str):
    """Ensure a track exists for a charm."""
    return ensure_track("charm", charm, track)


def ensure_snap_track(snap: str, track: str):
    """Ensure a track exists for a snap."""
    return ensure_track("snap", snap, track)


def main():
    FORMAT = "%(name)s:  %(asctime)s %(levelname)8s - %(message)s"
    logging.basicConfig(format=FORMAT)
    parser = argparse.ArgumentParser()
    parser.add_argument("kind", help="type of the entity", choices=["charm", "snap"])
    parser.add_argument("name", help="name of the entity")
    parser.add_argument("track", help="track to ensure")
    parser.add_argument(
        "-l",
        "--log",
        dest="loglevel",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Set the logging level",
    )
    args = parser.parse_args()
    if args.loglevel:
        log.setLevel(level=args.loglevel.upper())
    ensure_track(args.kind, args.name, args.track)


execd = __name__ == "__main__"
logger_name = sys.argv[0] if execd else __name__
log = logging.getLogger(logger_name)
if execd:
    main()
else:
    log.setLevel(logging.DEBUG)
