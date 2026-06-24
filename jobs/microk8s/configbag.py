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
        "1.35-strict",
        "1.36",
        "1.36-strict",
        "1.37",
        "1.37-strict",
        "1.38",
        "1.38-strict",
    ]


snap_name = "microk8s"
people_name = "microk8s-dev"
# Snapcraft channel used when triggering Launchpad builds for MicroK8s tracks
# that still build on core20 (everything prior to 1.34). Snapcraft 9.x dropped
# core20 support, and API-triggered builds ignore the recipe's pinned channel
# unless it is passed explicitly.
snapcraft_channel = "8.x/stable"
cachedir = os.getenv("WORKSPACE", default="/var/tmp/") + "/cache"
creds = os.getenv("LPCREDS")
github_repo = "github.com/canonical/microk8s"
