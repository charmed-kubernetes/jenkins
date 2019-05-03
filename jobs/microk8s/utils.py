import requests
import json


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


def compare_patch_with_alpha(a, b):
    """Compares two patch number string. The patch strings are of the form:
    0-alpha, 1-beta, 2-rc, 0

    Returns: 1 if a > b, 0 if a==b, -1 if a < b
    Raises ValueError if string is not correctly formated """
    if a == b:
        return 0

    aparts = a.split('-')
    bparts = b.split('-')

    # Comparing 0[-X] to 1[-Y]
    if aparts[0] != bparts[0]:
        arelease = int(aparts[0])
        brelease = int(bparts[0])
        if arelease > brelease:
            return 1
        if arelease < brelease:
            return -1
    else: # We are now at 1[-X] == 1[-Y]
        # Comparing 14 to 14-{whatever}
        if len(aparts) < len(bparts):
            return 1
        # Comparing 14-{whatever} to 14
        if len(aparts) > len(bparts):
            return -1

        # We are now at 1-{something} == 1-{somethingelse}
        # Comparing 14-{alpha} to 14-{beta,rc}
        if "alpha" in aparts[1] and any(r in bparts[1] for r in ['beta', 'rc']):
            return -1
        # Comparing 14-{alpha,beta} to 14-rc
        if any(r in aparts[1] for r in ['beta', 'alpha']) and "rc" in bparts[1]:
            return -1

        # We are now at 1-{something} == 1-{somethingelse}
        # were something > somethingelse
        return 1


def compare_releases(a, b):
    """Compares two version string.

    Returns: 1 if a > b, 0 if a==b, -1 if a < b
    Raises ValueError if string is not correctly formatted """

    major = 0
    minor = 1
    patch = 2
    revision = 3

    a = a.strip()
    b = b.strip()
    if a.startswith('v'):
        a = a[1:]
    if b.startswith('v'):
        b = b[1:]

    if a == b:
        return 0

    aparts = a.split('.')
    bparts = b.split('.')

    # Major part of a and b have to be digits
    amajor = int(aparts[major])
    bmajor = int(bparts[major])

    # Comparing 1.x to 2.y
    if amajor != bmajor:
        if amajor > bmajor:
            return 1
        elif amajor < bmajor:
            return -1

    # Since we reached this spot we have major sections equal

    # Minor part of a and b have to be digits
    aminor = int(aparts[minor])
    bminor = int(bparts[minor])

    # Comparing X.1 to X.12
    if aminor != bminor:
        if aminor > bminor:
            return 1
        elif aminor < bminor:
            return -1

    # Since we reached this spot we have major and minor sections equal
    patch_compare = compare_patch_with_alpha(aparts[patch], bparts[patch])
    if patch_compare != 0:
        return patch_compare

    # Since we reached this spot we have major, minor and patch sections equal
    # We know revision numbers exist because we have unequal version strings
    arevision = int(aparts[revision])
    brevision = int(bparts[revision])
    if arevision != brevision:
        if arevision > brevision:
            return 1
        elif arevision < brevision:
            return -1

    # Since we reached this spot we have major, minor, patch and revision sections equal
    # This should have been caught at the very beginning.
    assert False


def get_gh_releases():
    """Get all releases from GH.

    Returns the parsed json object or None on failure
    """
    releases_url = "https://api.github.com/repos/kubernetes/kubernetes/releases"
    r = requests.get(releases_url)
    if r.status_code == 200:
        releases = json.loads(r.content.decode().strip())
        return releases
    else:
        None


def get_latest_pre_release(track, patch):
    """
    Get the latest release for track and patch
    :param track: Something line 1.15, 1.16
    :param patch: alpha, beta, or rc
    :return: None if no pre-release is found of the latest pre-release name
    """
    releases = get_gh_releases()
    if not releases:
        return None

    search_version = "v{}.0-{}".format(track, patch)
    release_names = []
    for release in releases:
        if release['name'].startswith(search_version):
            release_names.append(release['name'][1:])

    if len(release_names) > 0:
        max_release = release_names[0]
        for release_candidate in release_names:
            if compare_releases(max_release, release_candidate) < 0:
                max_release = release_candidate
        return max_release
    else:
        return None


if __name__ == "__main__":
    """Tests..."""
    versions = [
        ('1.5.3', '1.3.4', 1),
        ('1.5.3', '1.6.4', 2),
        ('1.5.3', '1.5.3', 0),
        ('1.15.3', '1.15.4', 2),
        ('1.15.3', '1.15.2', 1),
        ('2.5.3', '3.3.4', 2),
        ('4.5.3', '3.3.4', 1),
        ('1.15.0-alpha.0', '1.15.0-alpha.0', 0),
        ('1.15.0-alpha.0', '1.15.0-alpha.1', 2),
        ('1.15.0-alpha.2', '1.15.0-alpha.1', 1),
        ('1.15.2-alpha.2', '1.15.0-alpha.1', 1),
        ('1.15.0-alpha.2', '1.15.2-alpha.1', 2),
        ('1.15.0-alpha.2', '1.15.2-alpha.2', 2),
        ('1.15.2-alpha.2', '1.15.0-beta.1', 1),
        ('1.15.0-alpha.2', '1.15.2-rc.1', 2),
        ('1.15.0-alpha.2', '1.15.2', 2),
        ('4.5.3', '3.3.0-alpha.2', 1),
    ]
    for pair in versions:
        res = compare_releases(pair[0], pair[1])
        if res > 0:
            print("{} newer than {}".format(pair[0], pair[1]))
            assert pair[2] == 1
        elif res < 0:
            print("{} older than {}".format(pair[0], pair[1]))
            assert pair[2] == 2
        else:
            print("{} and {} are equal".format(pair[0], pair[1]))
            assert pair[2] == 0

    releases = get_latest_pre_release("1","15","alpha")
    print(releases)

    releases = get_latest_pre_release("1","14","rc")
    print(releases)

    releases = get_latest_pre_release("1","12","rc")
    print(releases)
