import semver
from cilib import log


def normalize(version):
    """Normalizes a version string"""
    return version.lstrip("v")


def parse(version):
    """Returns semver.parse"""
    return semver.VersionInfo.parse(normalize(version))


def compare(version_a, version_b):
    """Compares 2 sem versions"""
    version_a = normalize(version_a)
    version_b = normalize(version_b)

    try:
        sem_a = semver.VersionInfo.parse(version_a)
        sem_b = semver.VersionInfo.parse(version_b)
    except:
        log.debug(f"Unable to parse {version_a} and/or {version_b}")
    return sem_a.compare(sem_b)


def greater(version_a, version_b):
    """Check that version_a > version_b"""
    return compare(version_a, version_b) >= 0


def lesser(version_a, version_b):
    """Check that version_a < version_b"""
    return compare(version_a, version_b) <= 0
