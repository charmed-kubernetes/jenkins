import requests
import semver


def latest():
    """ return latest version, this could be an alpha release
    """
    ret = requests.get(
        "https://storage.googleapis.com/kubernetes-release/release/latest.txt"
    )
    if ret.ok:
        ver_str = ret.text.strip().lstrip("v")
        return semver.parse(ver_str)
    return None


def stable():
    """ return latest stable
    """
    ret = requests.get(
        "https://storage.googleapis.com/kubernetes-release/release/stable.txt"
    )
    if ret.ok:
        ver_str = ret.text.strip().lstrip("v")
        return semver.parse(ver_str)
    return None
