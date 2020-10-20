import semver


def normalize(version):
    """Normalizes a version string"""
    return version.lstrip("v")


def parse(version):
    """Returns semver.parse"""
    return semver.parse(normalize(version))


def compare(version_a, version_b):
    """Compares 2 sem versions"""
    version_a = normalize(version_a)
    version_b = normalize(version_b)

    try:
        semver.parse(version_a)
        semver.parse(version_b)
    except:
        raise Exception(f"Unable to parse {version_a} and/or {version_b}")
    return semver.compare(version_a, version_b) >= 0


def greater(version_a, version_b):
    """Check that version_a > version_b"""
    version_a = normalize(version_a)
    version_b = normalize(version_b)

    try:
        semver.parse(version_a)
        semver.parse(version_b)
    except:
        raise Exception(f"Unable to parse {version_a} and/or {version_b}")
    return semver.compare(version_a, version_b) >= 0
