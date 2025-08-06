#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
from pathlib import Path
from urllib.request import urlopen, URLError
import re
import subprocess
import yaml

BASE_RE = re.compile(r"ubuntu (\d+\.\d+) \((\w+)\)")
GIT_DEP_RE = re.compile(
    r"""
    ^                                   # start of line
    (?P<name>[a-zA-Z0-9_\-\.]+)         # package name
    \s*@\s*                             # `@` surrounded by optional whitespace
    (?P<vcs>git\+)                      # VCS prefix (only git+ supported here)
    (?P<url>[^@#]+)                    # URL (no @ or #)
    @(?P<ref>[^#\s]+)                  # ref (commit, branch, or tag)
    (?:\#subdirectory=(?P<subdir>\S+))? # optional subdirectory
    """,
    re.VERBOSE
)
COMMIT_HASH_RE = re.compile(r"^[0-9a-fA-F]{7,40}$")


def flatten(l):
    return {k:v for sublist in l for k,v in sublist.items()}

def is_commit_hash(ref: str) -> bool:
    return bool(COMMIT_HASH_RE.fullmatch(ref))

def gh_rawfile(charm, path:str, branch:str="main", as_yaml:bool=True):
    """Return the URL to the raw file in the GitHub repository."""
    URL = "https://raw.githubusercontent.com/{repo}/refs/heads/{branch}/{path}"
    repo = charm["downstream"].replace(".git", "")
    if subdir := charm.get("subdir"):
        path = f"{subdir}/{path}"
    try:
        resp = urlopen(URL.format(repo=repo,branch=branch,path=path))
    except URLError as e:
        if e.code == 404:
            raise FileNotFoundError(f"File not found: {URL.format(repo=repo,branch=branch,path=path)}")
        else:
            raise e
    content = resp.read().decode("utf-8")
    if as_yaml:
        return yaml.safe_load(content)
    return content

def pin_deps_channels(name, charm, args):
    """Pin dependencies for the charm to release channel."""
    charmcraft, branch = None, f"release_{args.release}"
    try:
        charmcraft = gh_rawfile(charm, "charmcraft.yaml", branch)
    except FileNotFoundError:
        pass

    if not charmcraft:
        print(f"🚨 Charm {name} missing charmcraft.yaml")
        return

    charmcraft_part = charmcraft["parts"]["charm"]
    reactive = charmcraft_part.get("plugin") == "reactive"

    if reactive:
        env = charmcraft_part.get("build-environment") or []
        merged = {k: v for d in env for k, v in d.items()}
        release_branch = merged.get("RELEASE_BRANCH")
        if release_branch != branch:
            print(f"🚨 Charm {name} (reactive) has wrong {release_branch=}")
        return

    if requirements := gh_rawfile(charm, "requirements.txt", branch, as_yaml=False):
        for line in requirements.splitlines():
            if m := GIT_DEP_RE.match(line.strip()):
                ref = m.groupdict()["ref"] or ""
                if is_commit_hash(ref):
                    continue
                elif (ref == "main" or (ref.startswith("release")) and ref != branch):
                    print(f"🚨 Charm {name} (ops) dependency {m.groupdict()['name']} "
                          f"{m.groupdict()['ref']} != {branch}")


def has_noble_source(name, charm):
    """Check if the charm has noble support."""
    metadata, charmcraft = None, None
    try:
        metadata = gh_rawfile(charm, "metadata.yaml")
    except FileNotFoundError:
        pass

    try:
        charmcraft = gh_rawfile(charm, "charmcraft.yaml")
    except FileNotFoundError:
        pass

    if not metadata and not charmcraft:
        print(f"🚨 Charm {name} missing metadata.yaml and charmcraft.yaml")
        return

    has_noble = False
    if metadata:
        has_noble = "noble" in metadata.get("series", [])
    if charmcraft:
        if 'base' in charmcraft:
            has_noble |= "24.04" in charmcraft["base"]
        elif 'bases' in charmcraft:
            bases = [runs for base in charmcraft["bases"] for runs in base["run-on"]]
            has_noble |= any(base["channel"] == "24.04" for base in bases)

    if not has_noble:
        print(f"🚨 Charm {name} missing noble")
    else:
        print(f"✅ Charm {name} has noble")

def has_base(name, _charm, args):
    """Check if the charm has a noble in release/risk match."""
    release, risk, base = args.track, args.risk, args.base
    status = subprocess.check_output(["charmcraft","status", name, "--format", "json"])
    revs = yaml.safe_load(status)
    tracks = {k["track"]: k["mappings"] for k in revs}
    releases = tracks[release]
    noble_revs = {
        f'{k["base"]["channel"]} ({k["base"]["architecture"]})': r["revision"]
        for k in releases
        if k["base"]["channel"] in [base]
        for r in k["releases"]
        if r["channel"].endswith(risk)
    }
    if noble_revs and all(noble_revs.values()):
        print(f"✅ Charm {name} {release}/{risk} has {base=}")
    else:
        print(f"🚨 Charm {name} {release}/{risk} missing {base=}")


def risk_match(name, _charm, args):
    """Check if the charm has a beta match."""
    release, risk, bases = args.track, args.risk, args.bases
    status = subprocess.check_output(["charmcraft","status", name, "--format", "json"])
    revs = yaml.safe_load(status)
    tracks = {k["track"]: k["mappings"] for k in revs}
    latest, rel = tracks["latest"], tracks[release]
    beta_revs = lambda sequence:{
        f'{k["base"]["channel"]} ({k["base"]["architecture"]})': r["revision"]
        for k in sequence
        if k["base"]["channel"] in bases
        for r in k["releases"]
        if r["channel"].endswith(risk)
    }
    rel_beta, latest_beta = beta_revs(rel), beta_revs(latest)
    if rel_beta.items() <= latest_beta.items():
        print(f"✅ Charm {name} {release}/{risk} match latest/{risk}")
    else:
        print(f"🚨 Charm {name} {risk} doesn't match")
        print(f"  latest/{risk}: {latest_beta}")
        print(f"  {release}/{risk}:   {rel_beta}")


def runner(args):
    """Main function to check for things across all charms."""
    tags = args.tags
    path = Path("jobs/includes/charm-support-matrix.inc")
    supported_charms = flatten(yaml.safe_load(path.open()))
    k8s_charms = {
        k:v for k,v in supported_charms.items()
        if any(t in v.get("tags", []) for t in tags)
    }
    for name, charm in k8s_charms.items():
        yield name, charm


def main():
    parser = argparse.ArgumentParser(description="Check charm properties.")
    parser.add_argument(
        "--tags", default="k8s,k8s-operator",
        type=lambda s: s.strip().split(",") if s else [],
        help="Tags to filter charms (default: k8s, k8s-operator)"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # does the charm have noble support?
    sub = subparsers.add_parser("base", help="Check base support")
    sub.add_argument("track", help="Charm track")
    sub.add_argument("risk", help="Charm risk")
    sub.add_argument("base", help="Base channel to check (e.g., 24.04)")
    sub.set_defaults(func=has_base)

    # does the charm in latest/{risk} match {release}/{risk}?
    sub = subparsers.add_parser("match", help="Check charm risk match")
    sub.add_argument("track", help="Charm track")
    sub.add_argument("risk", help="Charm risk")
    sub.add_argument(
        "--bases",
        nargs="+",
        default=["22.04", "24.04"],
        help="Base channels to check (default: 22.04, 24.04)"
    )
    sub.set_defaults(func=risk_match)

    # does the charm pin dependencies to the release channel?
    sub = subparsers.add_parser("pin", help="Pin dependencies to release channel")
    sub.add_argument("release", help="Release version")
    sub.set_defaults(func=pin_deps_channels)

    args = parser.parse_args()
    for name, charm in runner(args):
        args.func(name, charm, args)

if __name__ == "__main__":
    main()
