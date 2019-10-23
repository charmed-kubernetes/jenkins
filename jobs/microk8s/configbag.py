import os
import platform


def get_arch():
    """
    Returns: the current architecture

    """
    arch_translate = {"aarch64": "arm64", "x86_64": "amd64"}

    # return arch_translate[platform.machine()]
    return os.environ.get("ARCH", "amd64")


def get_tracks(all=False):
    """

    Returns: the tracks valid for the architecture at hand

    """
    arch = get_arch()
    if arch == "arm64" and not all:
        # 1.12 and 1.13 removed temporarily because of failing builds blocking our CI
        return ["latest", "1.14", "1.15", "1.16", "1.17", "1.18", "1.19", "1.20"]
    else:
        # 1.10, 1.11, 1.12 and 1.13 removed temporarily because of failing builds blocking our CI
        return ["latest", "1.14", "1.15", "1.16", "1.17", "1.18", "1.19", "1.20"]


snap_name = "microk8s"
people_name = "microk8s-dev"
cachedir = os.getenv("WORKSPACE") + "/cache"
creds = os.getenv("LPCREDS")
