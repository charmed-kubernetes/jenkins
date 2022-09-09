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
        "1.21",
        "1.22",
        "1.22-eksd",
        "1.23",
        "1.23-eksd",
        "1.24",
        "1.24-eksd",
        "1.25",
        "1.26",
        "1.27",
        "1.25-strict",
    ]


snap_name = "microk8s"
people_name = "microk8s-dev"
cachedir = os.getenv("WORKSPACE", default="/var/tmp/") + "/cache"
creds = os.getenv("LPCREDS")
github_repo = "github.com/canonical/microk8s"
