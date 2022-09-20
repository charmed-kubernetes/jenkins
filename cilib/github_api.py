from dataclasses import dataclass, asdict
import logging
import os
from types import SimpleNamespace
from typing import Tuple
from urllib.parse import quote
import requests
import requests.auth


LOG = logging.getLogger("github_api")


class AuthSession(requests.Session):
    WRITE_METHODS = [
        "DELETE",
        "PATCH",
        "POST",
        "PUT",
    ]

    def __init__(self, auth: Tuple[str, str] = None, read_only=True) -> None:
        super().__init__()
        self._read_only = read_only

        user, passwd = auth or (
            quote(os.environ.get(_) or "") for _ in ["CDKBOT_GH_USR", "CDKBOT_GH_PSW"]
        )
        if all([user, passwd]):
            self.auth = requests.auth.HTTPBasicAuth(user, passwd)

    def request(self, method, *args, **kwargs):
        if self._read_only and method.upper() in self.WRITE_METHODS:
            _args = ", ".join(args)
            _kwds = ", ".join(f"{k}={v}" for k, v in kwargs.items())
            LOG.debug(f"{method}({_args}, {_kwds})")
            return SimpleNamespace(
                ok=False,
                status_code=403,
                text=f"{method} blocked by `read_only` flag",
                raise_for_status=lambda: None,
            )
        return super().request(method, *args, **kwargs)


@dataclass
class Repository:
    session: AuthSession
    owner: str
    repo: str

    _BASE_API: str = "https://api.github.com/repos"

    _GITTAG_API: str = "{_BASE_API}/{owner}/{repo}/git/tags"
    _GITREF_API: str = "{_BASE_API}/{owner}/{repo}/git/ref/{ref}"
    _GITREFS_API: str = "{_BASE_API}/{owner}/{repo}/git/refs"
    _REPO_API: str = "{_BASE_API}/{owner}/{repo}"
    _TAG_API: str = "{_BASE_API}/{owner}/{repo}/tags?per_page=100"
    _BRANCH_API: str = "{_BASE_API}/{owner}/{repo}/branches?per_page=100"
    _BRANCH_RENAME_API: str = "{_BASE_API}/{owner}/{repo}/branches/{branch}/rename"

    @classmethod
    def with_session(
        cls, owner: str, repo: str, auth: Tuple[str, str] = None, read_only=True
    ):
        session = AuthSession(auth=auth, read_only=read_only)
        return cls(session, owner, repo)

    @property
    def _render(self):
        d = asdict(self)
        str_d = {k: v for k, v in d.items() if isinstance(v, str)}
        str_d["repo"] = str_d["repo"].replace(".git", "")
        return str_d

    def _paginate(self, base_url: str, transform):
        result = []
        url = base_url.format(**self._render)
        while url:
            resp = self.session.get(url)
            result += [transform(t) for t in resp.json()]
            url = resp.links.get("next", {}).get("url")
        return result

    @property
    def tags(self):
        return self._paginate(self._TAG_API, lambda t: t["name"])

    @property
    def branches(self):
        return self._paginate(self._BRANCH_API, lambda t: t["name"])

    @property
    def default_branch(self):
        resp = self.session.get(self._REPO_API.format(**self._render))
        if resp.ok:
            return resp.json()["default_branch"]
        resp.raise_for_status()

    def rename_branch(self, from_name, to_name):
        """Rename git branch."""
        resp = self.session.post(
            self._BRANCH_RENAME_API.format(branch=from_name, **self._render),
            headers={"Accept": "application/vnd.github+json"},
            json={"new_name": to_name},
        )
        if not resp.ok:
            LOG.error(f"Rename Branch {resp.status_code}: {resp.text}")
        resp.raise_for_status()

    def copy_branch(self, from_name, to_name):
        """Copy git branch."""
        resp = self.get_ref(branch=from_name)
        resp = self.create_ref(branch=to_name, sha=resp["object"]["sha"])
        if not resp.ok:
            LOG.error(f"Copy Branch {resp.status_code}: {resp.text}")
        resp.raise_for_status()

    def tag_branch(self, branch, tag, message="built for the {tag} release") -> bool:
        """Annotate git tag based on branch."""
        resp = self.get_ref(branch=branch)
        sha, _type = resp["object"]["sha"], resp["object"]["type"]
        # create tag object
        return self.tag_commit(sha, tag, message=message.format(tag=tag), _type=_type)

    def tag_commit(self, sha, tag, message="Creating new tag: {tag}", _type="commit"):
        """Annotate git tag based on commit."""
        resp = self.session.post(
            self._GITTAG_API.format(**self._render),
            headers={"Accept": "application/vnd.github+json"},
            json=dict(tag=tag, message=message.format(tag=tag), object=sha, type=_type),
        )
        if not resp.ok:
            LOG.error(f"Tag Object {resp.status_code}: {resp.text}")
            return False

        # create tag reference
        resp = self.create_ref(tag=tag, sha=sha)
        if not resp.ok:
            LOG.error(f"Tag Reference {resp.status_code}: {resp.text}")
            return False
        return True

    def get_ref(self, tag=None, branch=None, raise_on_error=True):
        """Get git reference."""
        one_and_only_one = any((tag, branch)) and not all((tag, branch))
        assert one_and_only_one, "Either tag or branch should be defined"
        ref = f"tags/{tag}" if tag else f"heads/{branch}"
        resp = self.session.get(self._GITREF_API.format(**self._render, ref=ref))
        if raise_on_error:
            resp.raise_for_status()
        return resp.json()

    def create_ref(self, sha, tag=None, branch=None):
        """Create git reference (AKA lightweight tag)."""
        one_and_only_one = any((tag, branch)) and not all((tag, branch))
        assert one_and_only_one, "Either tag or branch should be defined"
        ref = f"refs/tags/{tag}" if tag else f"refs/heads/{branch}"
        resp = self.session.post(
            self._GITREFS_API.format(**self._render),
            headers={"Accept": "application/vnd.github+json"},
            json=dict(ref=ref, sha=sha),
        )
        return resp


if __name__ == "__main__":
    repo = Repository.with_session("charmed-kubernetes", "jenkins")
    print(repo.tags)
