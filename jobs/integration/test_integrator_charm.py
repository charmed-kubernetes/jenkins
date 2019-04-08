from pathlib import Path
import os
import sh
from .logger import log, log_calls, log_calls_async
import pytest
import requests
from .utils import asyncify

env = os.environ.copy()
CLOUD = env.get('CLOUD', 'aws')


def template_path():
    """ get correct template path for cloud
    """
    here = Path(__file__).absolute().parent
    return here / 'templates/integrator-charm-data' / CLOUD


@pytest.mark.asyncio
def test_create_storage():
    """ Test creating a storage class
    """
    kubectl_yml = template_path() / 'storage-class.yaml'
    sh.kubectl.create(f=kubectl_yml)
    pass

@pytest.mark.asyncio
def test_pv_claim():
    """ Test creating a persistent volume claim
    """
    kubectl_yml = template_path() / 'pv-claim.yaml'
    sh.kubectl.create(f=kubectl_yml)
    pass

@pytest.mark.asyncio
def test_bbox():
    """ Test creating a bbox pod
    """
    kubectl_yml = template_path() / 'bbox.yaml'
    sh.kubectl.create(f=kubectl_yml)
    pass


@pytest.mark.asyncio
def test_load_balancer():
    """ Performs a deployment of hello-world with newly created LB and attempts
    to do a requests.get and parse the html to verify the lb ip address is
    functioning appropriately.
    """
    # kubectl run hello-world --replicas=5 --labels="run=load-balancer-example" --image=gcr.io/google-samples/node-hello:1.0  --port=8080
    # kubectl expose deployment hello-world --type=LoadBalancer --name=hello
    pass
