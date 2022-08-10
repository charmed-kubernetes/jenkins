import argparse
from cilib.github_api import AuthSession, Repository
from itertools import chain
import logging
from pathlib import Path
import yaml


logging.basicConfig()
LOG = logging.getLogger("renamer")


def yaml_load(*args):
    return yaml.safe_load(Path(*args).read_text())


def bundle_load(*args):
    bundles = yaml_load(*args)
    for bundle in bundles:
        for _, params in bundle.items():
            if not params.get("downstream"):
                params["downstream"] = "charmed-kubernetes/bundle.git"
    return bundles


def comma_list(args):
    return args.split(",")


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
    session = AuthSession(read_only=args.dry_run)
    logging.root.setLevel(level=args.log_level)
    repo_map = {
        entity: Repository(session, *params["downstream"].split("/"))
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
                repo.tag_branch(args.branch, args.tag)
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


if __name__ == "__main__":
    args = parse_args()
    main(args)
