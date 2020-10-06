#!/usr/bin/env python3

import click
import os
import yaml
import tempfile
import semver
from sh.contrib import git
from cilib.run import cmd_ok
from cilib.git import remote_tags
from pathlib import Path


DEB_REPOS = ["kubectl", "kubeadm", "kubelet", "kubernetes-cni"]
VERSION_PPA = {
    "1.18": "ppa:k8s-maintainers/1.18",
    "1.19": "ppa:k8s-maintainers/1.19",
    "1.20": "ppa:k8s-maintainers/1.20",
}


class KubernetesRepo:
    def __init__(self, k8s_version, git_user):
        self.git_user = git_user
        self.base_url = f"git+ssh://{git_user}@git.launchpad.net"
        self.k8s_version = k8s_version

    def get_kubernetes_source(self):
        """Clones internal kubernetes source"""
        click.echo("Downloading internal kubernetes source repository")
        if not Path("k8s-internal-mirror").exists():
            cmd_ok(f"git clone {self.base_url}/k8s-internal-mirror")
            cmd_ok(f"git checkout {self.k8s_version}", cwd="k8s-internal-mirror")
        else:
            cmd_ok(f"git pull --ff-only", cwd="k8s-internal-mirror")

    def get_packaging_repos(self):
        """Downloads the required packaging repos"""
        click.echo("Downloading packaging repositories")
        for repo in DEB_REPOS:
            if not Path(repo).exists():
                cmd = f"git clone {self.base_url}/{repo}"
                click.echo(f":: {cmd}")
                cmd_ok(cmd)


class BuildRepo:
    def make_debs(self):
        """Builds the debian packaging for each component"""
        for repo in DEB_REPOS:
            cmd_ok(f"cp -a {repo}/* k8s-internal-mirror/.", shell=True)
            cmd_ok(f"debuild -us -uc", cwd="k8s-internal-mirror")
            cmd_ok(f"rm -rf debian")


@click.group()
def cli():
    pass


@cli.command()
def sync_tags():
    deb_list = Path("jobs/includes/k8s-deb-ppa-list.inc")
    supported_releases = []
    upstream_releases = remote_tags(
        "git+ssh://cdkbot@git.launchpad.net/k8s-internal-mirror"
    )

    click.echo(f"Writing deb version tags:")
    click.echo(upstream_releases)
    deb_list.write_text(
        yaml.dump(upstream_releases, default_flow_style=False, indent=2)
    )
    click.echo(f"Stored list at {str(deb_list)}")

    with tempfile.TemporaryDirectory() as tmpdir:
        env = os.environ.copy()
        repo = f"https://{env['CDKBOT_GH_USR']}:{env['CDKBOT_GH_PSW']}@github.com/charmed-kubernetes/jenkins"
        git.clone(repo, tmpdir)
        git.config("user.email", "cdkbot@gmail.com", _env=env, _cwd=tmpdir)
        git.config("user.name", "cdkbot", _env=env, _cwd=tmpdir)
        git.config("--global", "push.default", "simple", _cwd=tmpdir)

        output = Path(tmpdir) / str(deb_list)
        click.echo(f"Saving to {str(output)}")
        output.write_text(
            yaml.dump(upstream_releases, default_flow_style=False, indent=2)
        )
        cmd_ok(f"git add {str(output)}", cwd=tmpdir)
        ret = cmd_ok(["git", "commit", "-m", "Updating k8s deb tags list"], cwd=tmpdir)
        if not ret.ok:
            return
        click.echo(f"Committing to {repo}.")
        ret = cmd_ok(["git", "push", repo, "master"], cwd=tmpdir)
        if not ret.ok:
            raise SystemExit("Failed to commit latest deb tags.")

    return


@cli.command()
@click.option("--version", help="Kubernetes tag to build", required=True)
@click.option("--git-user", help="Git repo user", required=True, default="cdkbot")
def build_debs(version, git_user):
    _fmt_rel = version.lstrip("v")
    parsed_version = version
    try:
        parsed_version = semver.parse(_fmt_rel)
        parsed_version = f"{parsed_version['major']}.{parsed_version['minor']}"
    except ValueError as error:
        click.echo(f"Skipping invalid {_fmt_rel}: {error}")

    PPA = VERSION_PPA[parsed_version]
    click.echo(f"Selecting PPA: {PPA}")
    repo = KubernetesRepo(version, git_user)
    repo.get_kubernetes_source()
    repo.get_packaging_repos()

    build = BuildRepo()
    build.make_debs()


if __name__ == "__main__":
    cli()
