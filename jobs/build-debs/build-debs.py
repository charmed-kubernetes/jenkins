#!/usr/bin/env python3

import click
import yaml
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
    def __init__(self, k8s_version):
        self.base_url = "git+ssh://cdkbot@git.launchpad.net"
        self.k8s_version = k8s_version

    def get_kubernetes_source(self):
        """Clones internal kubernetes source"""
        click.echo("Downloading internal kubernetes source repository")
        cmd_ok(f"git clone {self.base_url}/k8s-internal-mirror")
        cmd_ok(f"git checkout {self.k8s_version}", cwd="k8s-internal-mirror")

    def get_packaging_repos(self):
        """Downloads the required packaging repos"""
        click.echo("Downloading packaging repositories")
        for repo in DEB_REPOS:
            click.echo(":: {self.base_url}/{repo}")
            cmd_ok(f"git clone {self.base_url}/{repo}")


class BuildRepo:
    def make_debs(self):
        """Builds the debian packaging for each component"""
        for repo in DEB_REPOS:
            cmd_ok(f"cp -a {repo}/* k8s-internal-mirror/.")
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
    click.echo(f"Stored list at f{str(deb_list)}")
    return


@cli.command()
@click.option("--version", "Kuberenetes major.minor to build", required=False)
@click.option("--ppa", "Kuberenetes PPA to upload", required=False)
def build_debs(version, ppa):
    PPA = VERSION_PPA[ppa]
    repo = KubernetesRepo(version)
    repo.get_kubernetes_source()
    repo.get_packaging_repos()

    build = BuildRepo()
    build.make_debs()


if __name__ == "__main__":
    cli()
