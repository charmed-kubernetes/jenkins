""" Git utils
"""

import sh


def remote_tags(url):
    """ Returns a list of remote tags
    """
    _tags = sh.sed(
        sh.sort(sh.git("ls-remote", "-t", "--refs", url), "-t", "/", "-k", 3, "-V"),
        "-E",
        "s/^[[:xdigit:]]+[[:space:]]+refs\\/tags\\/(.+)/\\1/g",
    ).stdout.decode()
    return _tags.split("\n")[:-1]


def remote_branches(url):
    """ Returns a list of remote branches
    """
    _tags = sh.sed(
        sh.sort(sh.git("ls-remote", "-h", "--refs", url), "-t", "/", "-k", 3, "-V"),
        "-E",
        "s/^[[:xdigit:]]+[[:space:]]+refs\\/heads\\/(.+)/\\1/g",
    ).stdout.decode()
    return _tags.split("\n")[:-1]


def branch_exists(repo, branch, env):
    """ Checks if a branch exists
    """
    try:
        sh.git("ls-remote", "--exit-code", "--heads", repo, branch, env=env)
    except sh.ErrorReturnCode_2 as e:
        return False
    return True
