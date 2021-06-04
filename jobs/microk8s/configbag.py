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
        "1.17",
        "1.18",
        "1.19",
        "1.20",
        "1.21",
        "1.22",
    ]


snap_name = "microk8s"
people_name = "microk8s-dev"
cachedir = os.getenv("WORKSPACE", default="/var/tmp/") + "/cache"
creds = os.getenv("LPCREDS")
