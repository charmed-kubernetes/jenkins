import os


def get_arch():
    """
    Returns: the current architecture

    """
    # return arch_translate[platform.machine()]
    return os.environ.get("ARCH", "amd64")


def get_tracks(all=False):
    """

    Returns: the tracks valid for the architecture at hand

    """
    return [
        "latest",
        "1.28",
        "1.28-strict",
        "1.29",
        "1.29-strict",
        "1.30",
        "1.30-strict",
        "1.31",
        "1.31-strict",
        "1.32",
        "1.32-strict",
        "1.33",
        "1.33-strict",
        "1.34",
        "1.34-strict",
        "1.35",
    ]


snap_name = "microk8s"
people_name = "microk8s-dev"
cachedir = os.getenv("WORKSPACE", default="/var/tmp/") + "/cache"
creds = os.getenv("LPCREDS")
github_repo = "github.com/canonical/microk8s"
