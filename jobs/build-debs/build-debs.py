#!/usr/bin/env python3

import click
from cilib.run import cmd_ok


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
@click.option("--version", "Kuberenetes major.minor to build", required=False)
def build_debs(version):
    PPA = VERSION_PPA[version]
    repo = KubernetesRepo(version)
    repo.get_kubernetes_source()
    repo.get_packaging_repos()

    build = BuildRepo()
    build.make_debs()


if __name__ == "__main__":
    cli()
