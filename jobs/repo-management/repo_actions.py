from dataclasses import dataclass, asdict
import argparse
from itertools import chain
import logging
from pathlib import Path
import os
from types import SimpleNamespace
from urllib.parse import quote

import requests
import requests.auth
import yaml


GH_SESSION = None
logging.basicConfig()
LOG = logging.getLogger("renamer")


def yaml_load(*args):
    return yaml.safe_load(Path(*args).read_text())


def bundle_load(*args):
    bundles = yaml_load(*args)
    for bundle in bundles:
        for _, params in bundle.items():
            if not params.get("downsteram"):
                params["downstream"] = "charmed-kubernetes/bundle.git"
    return bundles


def comma_list(args):
    return args.split(",")


class GHSession:
    def __init__(self, args) -> None:
        self.s = requests.Session()
        user, passwd = [
            quote(os.environ.get(_)) for _ in ["CDKBOT_GH_USR", "CDKBOT_GH_PSW"]
        ]
        if all([user, passwd]):
            self.s.auth = requests.auth.HTTPBasicAuth(user, passwd)
        self.args = args

    def post(self, *args, **kwargs):
        if self.args.dry_run:
            _args = ",".join(args)
            _kwds = ",".join(f"{k}={v}" for k, v in kwargs.items())
            LOG.debug(f"post({_args}, {_kwds})")
            return SimpleNamespace(ok=True)
        return self.s.post(*args, **kwargs)


@dataclass
class Repo:
    owner: str
    repo: str

    _TAG_API: str = "https://api.github.com/repos/{owner}/{repo}/tags?per_page=100"
    _GITTAG_API: str = "https://api.github.com/repos/{owner}/{repo}/git/tags"
    _GITREF_API: str = "https://api.github.com/repos/{owner}/{repo}/git/ref/{ref}"
    _GITREFS_API: str = "https://api.github.com/repos/{owner}/{repo}/git/refs"
    _BRANCH_API: str = (
        "https://api.github.com/repos/{owner}/{repo}/branches?per_page=100"
    )
    _BRANCH_RENAME_API: str = (
        "https://api.github.com/repos/{owner}/{repo}/branches/{branch}/rename"
    )

    @property
    def _render(self):
        d = asdict(self)
        return {k: v.replace(".git", "") for k, v in d.items()}

    @property
    def tags(self):
        resp = GH_SESSION.s.get(self._TAG_API.format(**self._render))
        return [t["name"] for t in resp.json()]

    @property
    def branches(self):
        resp = GH_SESSION.s.get(self._BRANCH_API.format(**self._render))
        return [t["name"] for t in resp.json()]

    def rename_branch(self, from_name, to_name):
        """Rename git branch."""
        resp = GH_SESSION.post(
            self._BRANCH_RENAME_API.format(branch=from_name, **self._render),
            headers={"Accept": "application/vnd.github+json"},
            json={"new_name": to_name},
        )
        if not resp.ok:
            LOG.error(f"Rename Branch {resp.status_code}: {resp.text}")

    def copy_branch(self, from_name, to_name):
        """Copy git branch."""
        resp = self.get_ref(branch=from_name)
        if "object" not in resp:
            LOG.error(f"Can't copy branch {from_name}: {resp}")
            return
        resp = self.create_ref(branch=to_name, sha=resp["object"]["sha"])
        if not resp.ok:
            LOG.error(f"Copy Branch {resp.status_code}: {resp.text}")

    def get_ref(self, tag=None, branch=None):
        """Get git reference."""
        if tag:
            url = self._GITREF_API.format(**self._render, ref=f"tags/{tag}")
        elif branch:
            url = self._GITREF_API.format(**self._render, ref=f"heads/{branch}")
        else:
            assert "Neither tag nor branch defined"
        resp = GH_SESSION.s.get(url)
        return resp.json()

    def create_ref(self, sha, tag=None, branch=None):
        """Create git reference."""
        if tag:
            ref = f"refs/heads/{tag}"
        elif branch:
            ref = f"refs/heads/{branch}"
        else:
            assert "Neither tag nor branch defined"
        resp = GH_SESSION.post(
            self._GITREFS_API.format(**self._render),
            headers={"Accept": "application/vnd.github+json"},
            json=dict(ref=ref, sha=sha),
        )
        return resp

    def tag_repo(self, branch, tag, message="built for the {tag} release"):
        """Annotate git tag based on branch."""
        resp = self.get_ref(branch=branch)
        sha, _type = resp["object"]["sha"], resp["object"]["type"]
        # create tag object
        resp = GH_SESSION.post(
            self._GITTAG_API.format(**self._render),
            headers={"Accept": "application/vnd.github+json"},
            json=dict(tag=tag, message=message.format(tag=tag), object=sha, type=_type),
        )
        if not resp.ok:
            LOG.error(f"Tag Object {resp.status_code}: {resp.text}")
            return

        # create tag reference
        resp = self.create_ref(tag=tag, sha=sha)
        if not resp.ok:
            LOG.error(f"Tag Reference {resp.status_code}: {resp.text}")
            return


def parse_args():
    parser = argparse.ArgumentParser("stable-branch-rename")
    parser.add_argument(
        "--charm-list", type=yaml_load, default=[], help="path to supported charms list"
    )
    parser.add_argument(
        "--layer-list", type=yaml_load, default=[], help="path to supported layers list"
    )
    parser.add_argument(
        "--bundle-list",
        type=bundle_load,
        default=[],
        help="path to supported bundle list",
    )
    parser.add_argument(
        "--filter-by-tags",
        type=comma_list,
        default=["k8s"],
        help="Filter based on support tags",
    )
    parser.add_argument(
        "--branch",
        type=str,
        help="Specify name of the working {branch}  eg. (release_1.24)",
    )
    parser.add_argument(
        "--tag",
        type=str,
        help="Specify name of a new tag at HEAD/{branch}, otherwise leave empty",
    )
    parser.add_argument(
        "--rename-branch",
        type=str,
        help="Specify new name for {branch}, otherwise leave empty",
    )
    parser.add_argument(
        "--copy-branch",
        type=str,
        help="Specify new name copied from {branch}, otherwise leave empty",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="Do not affect change on any repo.",
    )
    parser.add_argument(
        "--no-dry-run",
        action="store_false",
        dest="dry_run",
        help="Enact specified changes on repos.",
    )
    parser.add_argument(
        "--log-level", choices=logging._nameToLevel.keys(), default="INFO"
    )
    return parser.parse_args()


def main(args):
    global GH_SESSION
    GH_SESSION = GHSession(args)
    LOG.setLevel(level=args.log_level)
    repo_map = {
        entity: Repo(*params["downstream"].split("/"))
        for entities in chain(args.charm_list, args.layer_list, args.bundle_list)
        for entity, params in entities.items()
        if any(kw in args.filter_by_tags for kw in params.get("tags", []))
    }
    for entity, repo in repo_map.items():
        if args.branch and (not args.branch in repo.branches):
            LOG.info(f"Skipping {entity} since branch {args.branch} wasn't found")
            continue
        if args.tag:
            if args.tag in repo.tags:
                LOG.info(f"Skip Tagging {entity}, already has tag {args.tag}")
            elif not args.branch:
                LOG.warning(f"Skip Tagging {entity}, no branch specified")
            else:
                LOG.info(f"Tagging Repo {entity}/{args.branch} with {args.tag}")
                repo.tag_repo(args.branch, args.tag)
        if args.branch:
            if args.rename_branch:
                if args.rename_branch in repo.branches:
                    LOG.info(
                        f"Skipping Branch Rename {entity}, already has has branch {args.rename_branch}"
                    )
                else:
                    LOG.info(
                        f"Rename branch {entity}/{args.branch} to {args.rename_branch}"
                    )
                    repo.rename_branch(args.branch, args.rename_branch)
            elif args.copy_branch:
                if args.copy_branch in repo.branches:
                    LOG.info(
                        f"Skipping Branch Copy {entity}, already has has branch {args.copy_branch}"
                    )
                else:
                    LOG.info(
                        f"Copy branch {entity}/{args.branch} to {args.copy_branch}"
                    )
                    repo.copy_branch(args.branch, args.copy_branch)


if __name__ == "__main__":
    args = parse_args()
    main(args)
