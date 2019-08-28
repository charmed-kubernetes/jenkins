import requests
import json
import semver
from snapstore import Microk8sSnap


def upstream_release(release):
    """Return the latest stable k8s in the release series"""
    if release == "latest":
        release_url = "https://dl.k8s.io/release/stable.txt"
    else:
        release_url = "https://dl.k8s.io/release/stable-{}.txt".format(release)

    r = requests.get(release_url)
    if r.status_code == 200:
        return r.content.decode().strip()
    else:
        None


def compare_releases(a, b):
    """Compares two version string.

    Returns: 1 if a > b, 0 if a==b, -1 if a < b
    Raises ValueError if string is not correctly formatted """

    a = a.strip()
    b = b.strip()
    if a.startswith("v"):
        a = a[1:]
    if b.startswith("v"):
        b = b[1:]

    if a == b:
        return 0

    return semver.compare(a, b)


def get_gh_releases():
    """Get all releases from GH.

    Returns the parsed json object or None on failure
    """
    releases_url = "https://api.github.com/repos/kubernetes/kubernetes/releases"
    r = requests.get(releases_url)
    if r.status_code == 200:
        releases = json.loads(r.content.decode().strip())
        return releases
    else:
        None


def get_latest_pre_release(track, patch):
    """
    Get the latest release for track and patch
    :param track: Something line 1.15, 1.16
    :param patch: alpha, beta, or rc
    :return: None if no pre-release is found of the latest pre-release name
    """
    releases = get_gh_releases()
    if not releases:
        return None

    search_version = "v{}.0-{}".format(track, patch)
    release_names = []
    for release in releases:
        if release["name"].startswith(search_version):
            release_names.append(release["name"][1:])

    if len(release_names) > 0:
        max_release = release_names[0]
        for release_candidate in release_names:
            if compare_releases(max_release, release_candidate) < 0:
                max_release = release_candidate
        return max_release
    else:
        return None
