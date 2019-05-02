import requests


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
