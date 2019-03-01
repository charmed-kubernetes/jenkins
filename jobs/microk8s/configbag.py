import os
import platform


def get_arch():
    '''
    Returns: the current architecture

    '''
    arch_translate = {
        'aarch64': 'arm64',
        'x86_64': 'amd64'
    }

    return arch_translate[platform.machine()]


def get_tracks(all=False):
    '''

    Returns: the tracks valid for the architecture at hand

    '''
    arch = get_arch()
    if arch == 'arm64' and not all:
        return ["latest", "1.12", "1.13"]
    else:
        return ["latest", "1.10", "1.11", "1.12", "1.13"]


snap_name = "microk8s"
people_name = "microk8s-dev"
cachedir = os.getenv('WORKSPACE') + "/cache"
creds = os.getenv('LPCREDS')
