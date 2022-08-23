""" Git utils
"""

import logging
import sh
from subprocess import run
from .github_api import Repository
import requests
import requests.auth

log = logging.getLogger(__name__)


def default_gh_branch(repo: str, ignore_errors=False, auth=None):
    """
    Fetch the default GitHub branch.

    :param str repo: GitHub repo path expressed by $org/$repo
    :param bool ignore_errors: if errors are ignored, returns None
    :param tuple[str, str] auth: username/password used by basic-auth
    """
    org, repo = repo.split("/")
    gh_repo = Repository.with_session(org, repo, auth)
    try:
        return gh_repo.default_branch
    except requests.HTTPError:
        log.exception(f"HTTP error connecting to {repo}")
        if not ignore_errors:
            raise


def clone(url, **subprocess_kwargs):
    """Clone package repo"""
    run(["git", "clone", url], **subprocess_kwargs)


def fetch(origin="origin", **subprocess_kwargs):
    """Fetch"""
    run(["git", "fetch", origin], **subprocess_kwargs)


def checkout(ref, new_branch=False, force=False, **subprocess_kwargs):
    """Checkout ref"""
    cmd = ["git", "checkout"]
    if new_branch:
        cmd.append("-b")
    if force:
        cmd.append("-f")
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


def merge(origin="origin", ref="master", **subprocess_kwargs):
    """Merges branch"""
    run(["git", "merge", f"{origin}/{ref}"], **subprocess_kwargs)


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
