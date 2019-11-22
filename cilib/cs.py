# charmstore

import sh
import requests
import click
import yaml
from cilib.run import capture


def get_charmstore_rev_url(entity, channel):
    # Grab charmstore revision for channels charm
    response = capture(["charm", "show", entity, "--channel", channel, "id"])
    response = yaml.safe_load(response.stdout.decode().strip())
    return response["id"]["Id"]


def download(entity, channel, fname):
    entity_p = get_charmstore_rev_url(entity, channel).lstrip("cs:")
    url = f"https://api.jujucharms.com/charmstore/v5/{entity_p}/archive/{fname}"
    click.echo(f"Downloading {fname} from {url}")
    return requests.get(url)
