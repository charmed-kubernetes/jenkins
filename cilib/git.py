""" Git utils
"""

import sh
from subprocess import run


def clone(url, **subprocess_kwargs):
    """Clone package repo"""
    run(["git", "clone", url], **subprocess_kwargs)


def checkout(ref, new_branch=False, **subprocess_kwargs):
    """Checkout ref"""
    cmd = ["git", "checkout"]
    if new_branch:
        cmd.append("-b")
    cmd.append(ref)
    run(cmd, **subprocess_kwargs)


def add(files, **subprocess_kwargs):
    """Add files to git repo"""
    for fn in files:
        run(["git", "add", fn], **subprocess_kwargs)


def commit(message, **subprocess_kwargs):
    """Add commit to repo"""
    run(["git", "config", "user.email", "cdkbot@gmail.com"], **subprocess_kwargs)
    run(["git", "config", "user.name", "cdkbot"], **subprocess_kwargs)
    run(["git", "config", "--global", "push.default", "simple"], **subprocess_kwargs)

    run(["git", "commit", "-m", message], **subprocess_kwargs)


def push(origin="origin", ref="master", **subprocess_kwargs):
    """Pushes commit to repo"""
    run(["git", "push", origin, ref], **subprocess_kwargs)


def remote_add(origin, url, **subprocess_kwargs):
    """Add remote to repo"""
    run(["git", "remote", "add", origin, url], **subprocess_kwargs)


def remote_tags(url, **subprocess_kwargs):
    """Returns a list of remote tags"""
    _tags = sh.sed(
        sh.sort(sh.git("ls-remote", "-t", "--refs", url), "-t", "/", "-k", 3, "-V"),
        "-E",
        "s/^[[:xdigit:]]+[[:space:]]+refs\\/tags\\/(.+)/\\1/g",
    ).stdout.decode()
    return _tags.split("\n")[:-1]


def remote_branches(url, **subprocess_kwargs):
    """Returns a list of remote branches"""
    _tags = sh.sed(
        sh.sort(sh.git("ls-remote", "-h", "--refs", url), "-t", "/", "-k", 3, "-V"),
        "-E",
        "s/^[[:xdigit:]]+[[:space:]]+refs\\/heads\\/(.+)/\\1/g",
    ).stdout.decode()
    _tags = _tags.split("\n")[:-1]
    return [tag for tag in _tags if tag != "master"]


def branch_exists(repo, branch, **subprocess_kwargs):
    """checks if a branch exists"""
    try:
        sh.git("ls-remote", "--exit-code", "--heads", repo, branch, **subprocess_kwargs)
    except sh.ErrorReturnCode_2 as e:
        return False
    return True
