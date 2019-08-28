#!/usr/bin/env python3
import sh
import json
import click
sh.apt("clean")
sh.rm("-rf", "/var/log/*")
sh.rm("-rf", "/var/lib/jenkins/.cache/*")
sh.docker.image.prune('-a', '--filter', "until=24h", '--force')
sh.docker.container.prune('--filter', "until=24h", '--force')
sh.du('-h', '--max-depth=1', '/var/lib')
sh.df('-h')

try:
    juju_controllers = json.loads(sh.juju.controllers('--format', 'json').stdout.decode())
    if juju_controllers:
        for name, _ in juju_controllers:
            try:
                sh.juju('destroy-controller', '--destroy-all-models', '--destroy-storage', '-y', name)
            except sh.ErrorReturnCode as e:
                click.echo(f"Error destroying {e}, continuing...")
except sh.ErrorReturnCode as e:
    click.echo(f"Error reading controller: {e.stderr.decode()}, continuing...")
containers = json.loads(sh.lxc.query('/1.0/containers').stdout.decode())
click.echo(containers)
for container in containers:
    sh.lxc.delete('--force', container)

storage_pools = json.loads(sh.lxc.query('/1.0/storage-pools').stdout.decode())
click.echo(storage_pools)
for storage in storage_pools:
    storage_name = storage.split('/')[-1]
    volumes = json.loads(sh.lxc.query(f"/1.0/storage-pools/{storage_name}/volumes").stdout.decode())
    click.echo(volumes)
    for volume in volumes:
        volume_name = volume.split('/')[-1]
        click.echo(f"Deleting {volume_name}")
        sh.lxc.storage.volume.delete(storage_name, f"custom/{volume_name}")
    try:
        sh.lxc.storage.delete(storage_name)
    except sh.ErrorReturnCode as e:
        click.echo(f"Error removing {e}, continuing...")

sh.rm("-rf", "/var/lib/jenkins/venvs")
