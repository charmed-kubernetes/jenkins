#!/usr/bin/env python3

import click
import os
import yaml
import tempfile
import semver
import uuid
from subprocess import run
from sh.contrib import git
from cilib.run import cmd_ok, capture
from cilib.git import remote_tags
from pathlib import Path


CORE_COMPONENTS = ["kubectl", "kubeadm", "kubelet", "cri-tools"]
VERSION_PPA = {
    "1.18": "ppa:k8s-maintainers/1.18",
    "1.19": "ppa:k8s-maintainers/1.19",
    "1.20": "ppa:k8s-maintainers/1.20",
}


@click.group()
def cli():
    pass


class Git:
    """Base git class

    Required attributes:
    repo - git url to access
    ref - branch or tag to reference
    """

    def clone(self, **subprocess_kwargs):
        """Clone package repo"""
        cmd_ok(f"git clone {self.repo}", **subprocess_kwargs)

    def checkout(self, **subprocess_kwargs):
        """Checkout ref"""
        cmd_ok(f"git checkout {self.ref}", **subprocess_kwargs)

    def commit(self, message, **subprocess_kwargs):
        """Add commit to repo"""
        run(["git", "config", "user.email", "cdkbot@gmail.com"], **subprocess_kwargs)
        run(["git", "config", "user.name", "cdkbot"], **subprocess_kwargs)
        run(
            ["git", "config", "--global", "push.default", "simple"], **subprocess_kwargs
        )
        run(["git", "add", "debian/changelog"], **subprocess_kwargs)
        run(["git", "commit", "-m", message], **subprocess_kwargs)

    def push(self, origin="origin", **subprocess_kwargs):
        """Pushes commit to repo"""
        run(["git", "push", "origin", self.ref], **subprocess_kwargs)


class DebBuilder:
    def bump_revision(self, **subprocess_kwargs):
        """Bumps upstream revision for builds"""
        cmd_ok("dch -U 'Automated Build' -D focal", **subprocess_kwargs)

    def source(self, sign_key, include_source=False, **subprocess_kwargs):
        """Builds the source deb package"""
        cmd = ["dpkg-buildpackage", "-S", f"--sign-key={sign_key}"]
        if not include_source:
            cmd.append("-sd")
        click.echo(f"Building package: {cmd}")
        run(cmd, **subprocess_kwargs)

    def cleanup_source(self, **subprocess_kwargs):
        run("rm -rf *.changes", shell=True, **subprocess_kwargs)

    def cleanup_debian(self, **subprocess_kwargs):
        run(["rm", "-rf", "debian"], **subprocess_kwargs)

    def upload(self, ppa, **subprocess_kwargs):
        """Uploads source packages via dput"""
        for changes in list(Path(".").glob("*changes")):
            cmd_ok(f"dput {ppa} {str(changes)}", **subprocess_kwargs)


class PackageComponentRepo(Git, DebBuilder):
    """Represents the debian packaging repos"""

    def __init__(self, name, git_user, ref="master"):
        """
        ref: git tag or branch to checkout
        """
        self.name = name
        self.git_user = git_user
        self.repo = f"git+ssh://{git_user}@git.launchpad.net/{self.name}"
        self.ref = ref

    def __str__(self):
        return (
            f"<PackageComponentRepo: {self.name} " f"Repo: {self.repo} Ref: {self.ref}>"
        )


class UpstreamComponentRepo(Git):
    """Represents the upstream source to be included in the debian packaging"""

    def __init__(self):
        self.repo = None
        self.git_user = None
        self.ref = None
        self.name = None


class KubernetesUpstreamComponentRepo(UpstreamComponentRepo):
    def __init__(self, git_user, ref="master"):
        super().__init__()
        self.name = "k8s-internal-mirror"
        self.git_user = git_user
        self.ref = ref
        self.repo = f"git+ssh://{git_user}@git.launchpad.net/{self.name}"


class CriToolsUpstreamComponentRepo(UpstreamComponentRepo):
    def __init__(self, ref="v1.19.0"):
        super().__init__()
        self.name = "cri-tools"
        self.ref = ref
        self.repo = f"https://github.com/kubernetes-sigs/{self.name}.git"

class CNIPluginsUpstreamComponentRepo(UpstreamComponentRepo):
    def __init__(self, ref="v0.8.7"):
        super().__init__()
        self.name = "plugins"
        self.ref = ref
        self.repo = f"https://github.com/containernetworking/{self.name}.git"


@cli.command()
@click.option("--ref", help="Kubernetes tag to build", required=True)
@click.option("--git-user", help="Git repo user", default="k8s-team-ci")
@click.option("--sign-key", help="GPG Sign key ID", required=True)
@click.option(
    "--include-source", help="Include orig.tar.gz source in builds", is_flag=True
)
@click.option("--package", help="Only build specific package", multiple=True)
def build_debs(ref, git_user, sign_key, include_source, package):
    _fmt_rel = ref.lstrip("v")

    # Get major.minor, this will be used when checking out branches in the debian package repo
    # and selecting a proper PPA
    parsed_version = ref
    try:
        parsed_version = semver.parse(_fmt_rel)
        parsed_version = f"{parsed_version['major']}.{parsed_version['minor']}"
    except ValueError as error:
        raise Exception(f"Skipping invalid {_fmt_rel}: {error}")

    PPA = VERSION_PPA[parsed_version]
    click.echo(f"Selecting PPA: {PPA}")

    # Core Packages to build
    upstreams = {
        KubernetesUpstreamComponentRepo(git_user, ref): [
            "kubectl",
            "kubelet",
            "kubeadm",
        ],
        CriToolsUpstreamComponentRepo(): ["cri-tools"],
        CNIPluginsUpstreamComponentRepo(): ["kubernetes-cni"],
    }
    for upstream, components in upstreams.items():
        click.echo(f"Grabbing upstream: {upstream.name}: {components}")
        upstream.clone()
        for component in components:
            if package and component not in package:
                click.echo(
                    f"Skipping {component} as it was not specified with --package"
                )
                continue
            with tempfile.TemporaryDirectory() as tmpdir:
                build = PackageComponentRepo(component, git_user, parsed_version)
                click.echo(f"Building component {build.name}")
                build.clone(cwd=tmpdir)
                build.checkout(cwd=f"{tmpdir}/{build.name}")
                build.bump_revision(cwd=f"{tmpdir}/{build.name}")
                run(f"cp -a {tmpdir}/{build.name}/* {upstream.name}/.", shell=True)
                build.source(sign_key, include_source, cwd=upstream.name)
                build.commit("Automated Build", cwd=f"{tmpdir}/{build.name}")
                build.push(cwd=f"{tmpdir}/{build.name}")
                build.upload(PPA)
                build.cleanup_source()
                build.cleanup_debian(cwd=upstream.name)


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


if __name__ == "__main__":
    cli()
