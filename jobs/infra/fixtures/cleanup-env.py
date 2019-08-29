#!/usr/bin/env python3
from subprocess import run, CalledProcessError
import json
import click

def sh(args, **kwargs):
    click.echo(args)
    try:
        output = run(args, capture_output=True, **kwargs).decode("utf-8")
    except CalledProcessError as e:
        msg = e.stdout.decode("utf-8") + e.stderr.decode("utf-8")
        click.secho(msg, fg="red", bold=True)
        raise
    click.echo(output)
    return output


sh(["sudo", "apt", "clean"])
sh(["rm", "-rf", "/var/log/*"])
sh(["rm", "-rf", "/var/lib/jenkins/.cache/*"])
sh(["sudo", "docker", "image", "prune", "-a", "--filter", "until=24h", "--force"])
sh(["sudo", "docker", "container", "prune", "--filter", "until=24h", "--force"])
sh(["du", "-h", "--max-depth=1", "/var/lib"])
sh(["df", "-h"])

try:
    juju_controllers = json.loads(
        sh(["juju", "controllers", "--format", "json"])
    )
    if juju_controllers:
        for name, _ in juju_controllers:
            try:
                sh(["juju",
                    "destroy-controller",
                    "--destroy-all-models",
                    "--destroy-storage",
                    "-y",
                    name]
                )
            except CalledProcessError as e:
                click.echo(f"Error destroying {e}, continuing...")
except CalledProcessError as e:
    click.echo(f"Error reading controller: {e.stderr.decode()}, continuing...")
containers = json.loads(sh("sudo", "lxc", "query", "/1.0/containers"))
click.echo(containers)
for container in containers:
    sh(["sudo", "lxc", "--force", container])

storage_pools = json.loads(sh(["sudo", "lxc", "query", "/1.0/storage-pools"]))
click.echo(storage_pools)
for storage in storage_pools:
    storage_name = storage.split("/")[-1]
    volumes = json.loads(
        sh(["sudo", "lxc", "query", f"/1.0/storage-pools/{storage_name}/volumes"])
    )
    click.echo(volumes)
    for volume in volumes:
        volume_name = volume.split("/")[-1]
        click.echo(f"Deleting {volume_name}")
        sh(["sudo", "lxc", "storage", "volume", "delete", storage_name, f"custom/{volume_name}"])
    try:
        sh(["sudo", "lxc", "storage", "delete", storage_name])
    except CalledProcessError as e:
        click.echo(f"Error removing {e}, continuing...")

sh(["rm", "-rf", "/var/lib/jenkins/venvs"])
