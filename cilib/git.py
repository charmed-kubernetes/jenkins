""" Git utils
"""

import logging
import sh
import re
from subprocess import run
from typing import Dict, List
from .github_api import Repository
import requests
import requests.auth
from retry import retry

log = logging.getLogger(__name__)


def _natural_sort_key(s, _nsre=re.compile("([0-9]+)")):
    return [int(text) if text.isdigit() else text for text in _nsre.split(s)]


def default_gh_branch(repo: str, ignore_errors=False, auth=None):
    """
    Fetch the default GitHub branch.

    :param str repo: GitHub repo path expressed by $org/$repo
    :param bool ignore_errors: if errors are ignored, returns None
    :param tuple[str, str] auth: username/password used by basic-auth
    """
    try:
        org, repo = repo.split("/")
    except ValueError:
        # Likely not a github repo since theres no org/repo
        if not ignore_errors:
            raise
        return None

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


def status(**subprocess_kwargs) -> List[Dict[str, str]]:
    """Show any uncommitted files in a git repo.

    Returns:
        List[Dict[str, str]]: A list of uncommitted files objects and their status.

        key values are the file names and the values are the status of the file.
        https://git-scm.com/docs/git-status
    """
    cmd = ["git", "status", "--porcelain"]
    output = run(cmd, capture_output=True, text=True, **subprocess_kwargs)

    def _mk_status(line):
        status = line[:2]
        path, *orig_path = line[3:].split(" -> ", maxsplit=1)
        if orig_path:
            return {"status": status, "path": path, "orig_path": orig_path[0]}
        else:
            return {"status": status, "path": path}

    return [_mk_status(line) for line in output.stdout.splitlines()]


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
    refs = sh.git("ls-remote", "-t", "--refs", url)
    tags = [line.split("/")[2] for line in refs.splitlines()]
    return sorted(tags, key=_natural_sort_key)


# retry because this fails often against git.launchpad.net
@retry(delay=1, backoff=2, tries=7)  # exponential, fails after ~63 seconds
def remote_branches(url, **subprocess_kwargs):
    """Returns a list of remote branches"""
    refs = sh.git("ls-remote", "-h", "--refs", url)
    tags = ["/".join(line.split("/")[2:]) for line in refs.splitlines()]
    branches = ["main", "master"]  # wokeignore:rule=master
    return sorted(filter(lambda t: t not in branches, tags), key=_natural_sort_key)


def branch_exists(repo, branch, **subprocess_kwargs):
    """checks if a branch exists"""
    try:
        sh.git("ls-remote", "--exit-code", "--heads", repo, branch, **subprocess_kwargs)
    except sh.ErrorReturnCode_2 as e:
        return False
    return True
