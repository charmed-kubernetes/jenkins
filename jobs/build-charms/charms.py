"""
charms.py - Interface to building and publishing charms

Usage:

  tox -e py36 -- python3 jobs/build-charms/charms.py build \
     --repo-path ../../layer-canal/ --out-path $HOME/charms/builds/canal

  tox -e py36 -- python3 jobs/build-charms/charms.py --help
"""

import os
from glob import glob
from pathlib import Path
from pprint import pformat

import click
import sh
import yaml


@click.group()
def cli():
    pass

@cli.command()
@click.option('--repo-path', required=True, help='Path of charm vcs repo')
@click.option('--out-path', required=True, help='Path of built charm')
def build(repo_path, out_path):
    for line in sh.charm.build(
            r=True, no_local_layers=True, force=True, v=True,
            _cwd=repo_path, _iter=True, _err_to_out=True):
        click.echo(line.strip())
    sh.charm.proof(_cwd=out_path)

@cli.command()
@click.option('--repo-path', required=True, help='Path of charm vcs repo')
@click.option('--out-path', required=True, help='Path of built charm')
@click.option('--charm-entity', required=True, help='Charm entity path (ie. cs~containers/flannel)')
def push(repo_path, out_path, charm_entity):
    git_commit = sh.git('rev-parse', 'HEAD', _cwd=repo_path)
    git_commit = git_commit.stdout.decode().strip()
    click.echo("Grabbing git revision {}".format(git_commit))

    # Build a list of `oci-image` resources that have `upstream-source` defined,
    # which is added for this logic to work.
    resources = yaml.load(Path(out_path).joinpath('metadata.yaml').read_text()).get('resources', {})
    images = {
        name: details['upstream-source']
        for name, details in resources.items()
        if details['type'] == 'oci-image' and details.get('upstream-source')
    }

    click.echo(f'Found {len(images)} oci-image resources:\n{pformat(images)}\n')

    for image in images.values():
        click.echo(f'Pulling {image}...')
        sh.docker.pull(image)

    # Convert the image names and tags to `--resource foo=bar` format
    # for passing to `charm push`.
    resource_args = [
        arg
        for name, image in images.items()
        for arg in ('--resource', f'{name}={image}')
    ]

    out = sh.charm.push(out_path, charm_entity, *resource_args)
    click.echo(f'Charm push returned: {out}')
    # Output includes lots of ansi escape sequences from the docker push,
    # and we only care about the first line, which contains the url as yaml.
    out = yaml.load(out.stdout.decode().strip().splitlines()[0])
    click.echo("Setting {} metadata: {}".format(out['url'],
                                                git_commit))
    sh.charm.set(out['url'], 'commit={}'.format(git_commit))

@cli.command()
@click.option('--charm-entity', required=True, help='Charmstore entity id (ie. cs~containers/flannel)')
@click.option('--channel', required=True, help='Charm channel to display info from')
def show(charm_entity, channel):
    click.echo()
    click.echo(sh.charm.show(charm_entity, channel=channel))

@cli.command()
@click.option('--charm-entity', required=True, help='Charmstore entity id (ie. cs~containers/flannel)')
@click.option('--from-channel', required=True, help='Charm channel to publish from')
@click.option('--to-channel', required=True, help='Charm channel to publish to')
def promote(charm_entity, from_channel, to_channel):
    charm_id = sh.charm.show(charm_entity, '--channel', from_channel, 'id')
    charm_id = yaml.load(charm_id.stdout.decode())
    resources_args = []
    try:
        resources = sh.charm('list-resources', charm_id['id']['Id'], channel=from_channel, format='yaml')
        resources = yaml.load(resources.stdout.decode())
        if resources:
            resources_args = [
                ('--resource', '{}-{}'.format(
                    resource['name'], resource['revision']))
                for resource in resources]
    except sh.ErrorReturnCode_1:
        click.echo("No resources for {}".format(charm_id))
    sh.charm.release(charm_id['id']['Id'], '--channel', to_channel, *resources_args)

@cli.command()
@click.option('--charm-entity', required=True, help='Charmstore entity id (ie. cs~containers/flannel)')
@click.option('--channel', required=True, default='unpublished', help='Charm channel to query entity')
@click.option('--builder', required=True, help='Path of resource builder')
@click.option('--out-path', required=True, help='Temporary storage of built charm resources')
@click.option('--resource-spec', required=True, help='YAML Spec of resource keys and filenames')
def resource(charm_entity, channel, builder, out_path, resource_spec):
    out_path = Path(out_path)
    resource_spec = yaml.load(Path(resource_spec).read_text())
    resource_spec_fragment = resource_spec.get(charm_entity, None)
    click.echo(resource_spec_fragment)
    if not resource_spec_fragment:
        raise SystemExit('Unable to determine resource spec for entity')

    os.makedirs(str(out_path), exist_ok=True)
    charm_id = sh.charm.show(charm_entity, '--channel', channel, 'id')
    charm_id = yaml.load(charm_id.stdout.decode())
    try:
        resources = sh.charm('list-resources', charm_id['id']['Id'], channel=channel, format='yaml')
    except sh.ErrorReturnCode_1:
        click.echo('No resources found for {}'.format(charm_id))
        return
    resources = yaml.load(resources.stdout.decode())
    builder_sh = Path(builder).absolute()
    click.echo(builder_sh)
    for line in sh.bash(str(builder_sh), _cwd=out_path, _iter=True, _err_to_out=True):
        click.echo(line.strip())
    for line in glob('{}/*'.format(out_path)):
        resource_path = Path(line)
        resource_fn = resource_path.parts[-1]
        resource_key = resource_spec_fragment.get(resource_fn, None)
        if resource_key:
            out = sh.charm.attach(charm_entity, '--channel', channel, '{}={}'.format(resource_key, resource_path))
            click.echo(out)



if __name__ == '__main__':
    cli()
