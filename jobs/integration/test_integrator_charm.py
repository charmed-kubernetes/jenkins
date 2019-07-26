from pathlib import Path
import os
import sh
import pytest
import requests
import yaml
from .utils import asyncify, _cloud_from_env

env = os.environ.copy()


def template_path():
    """ get correct template path for cloud
    """
    here = Path(__file__).absolute().parent
    return here / "templates/integrator-charm-data" / _cloud_from_env()


@pytest.fixture(scope="function")
def setup_storage_elb_resource(request):
    """ Sets up and tearsdown k8s resources
    """

    def setup_storage_elb_resource_teardown():
        print("Perform teardown of resources")

    storage_yml = template_path() / "storage-class.yaml"
    sh.kubectl.create(f=str(storage_yml))

    pv_claim_yml = template_path() / "pv-claim.yaml"
    sh.kubectl.create(f=str(pv_claim_yml))
    request.addfinalizer(setup_storage_elb_resource_teardown)

    # bbox_yml = template_path() / 'bbox.yaml'
    # sh.kubectl.create(f=str(bbox_yml))


@pytest.mark.asyncio
async def test_load_balancer(setup_storage_elb_resource):
    """ Performs a deployment of hello-world with newly created LB and attempts
    to do a requests.get and parse the html to verify the lb ip address is
    functioning appropriately.
    """
    sh.kubectl.run(
        "hello-world",
        replicas=5,
        labels="run=load-balancer-example",
        image="gcr.io/google-samples/node-hello:1.0",
        port=8080,
    )
    sh.kubectl.expose("deployment", "hello-world", type="LoadBalancer", name="hello")
    out = sh.kubectl.get("svc", o="yaml", selector="run=load-balancer-example")
    svc = yaml.safe_load(out.stdout.decode("utf8"))
    lb_ip = svc["status"]["loadBalancer"]["ingress"][0]
    set_url = f"{lb_ip}:8080"
    html = await asyncify(requests.get)(set_url)
    assert "Hello Kubernetes!" in html.content
