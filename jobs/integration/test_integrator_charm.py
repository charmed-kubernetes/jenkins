import asyncio
import logging
from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path
import os
import sh
import pytest
from typing import Any, List, Tuple, Mapping
import yaml

import jinja2
from retry import retry

from .utils import kubectl_apply, kubectl_delete

env = os.environ.copy()
logger = logging.getLogger(__name__)


class Tree(Enum):
    IN_TREE = auto()
    OUT_OF_TREE = auto()


@dataclass
class ProviderSupport:
    application: str
    storage_class: str
    out_relations: List[Tuple[str, str]]
    in_relations: List[Tuple[str, str]]
    config: Mapping[str, str] = field(default_factory=dict)
    in_tree_until: str = "999.0"
    trust: bool = False


TEMPLATE_PATH = Path(__file__).absolute().parent / "templates/integrator-charm-data"


def _prepare_relation(linkage, model, add=True):
    left, right = linkage
    app, left_relation = left.split(":")
    left_app = model.applications[app]
    if add:
        return left_app.add_relation(left_relation, right)
    return left_app.remove_relation(left_relation, right)


def get_provider(cloud):
    provider_file = TEMPLATE_PATH / cloud / "out-of-tree.yaml"
    config = yaml.safe_load(provider_file.read_text())
    return ProviderSupport(**{k.replace("-", "_"): config[k] for k in config})


@pytest.fixture(scope="module", params=[Tree.IN_TREE, Tree.OUT_OF_TREE])
async def storage_class(tools, model, request, cloud):
    provider = get_provider(cloud)
    out_of_tree = request.param is Tree.OUT_OF_TREE

    worker_app = model.applications["kubernetes-worker"]
    k8s_version_str = worker_app.data["workload-version"]
    k8s_minor_version = tuple(int(i) for i in k8s_version_str.split(".")[:2])
    support_version = tuple(int(i) for i in provider.in_tree_until.split(".")[:2])

    if not out_of_tree and k8s_minor_version > support_version:
        pytest.skip(
            f"In-Tree storage tests do not work in {cloud} after {provider.in_tree_until}."
        )
    elif out_of_tree and k8s_minor_version <= support_version:
        pytest.skip(
            f"Out-of-Tree storage not tested on {cloud} <= {provider.in_tree_until}."
        )

    provider_app = provider.application
    provider_deployed = provider_app in model.applications
    expected_apps = set(model.applications)

    if out_of_tree and not provider_deployed:
        logger.info(f"Adding provider={provider_app} to model.")
        # deploy provider.application
        await model.deploy(
            provider_app,
            channel=tools.charm_channel,
            trust=provider.trust,
            config=provider.config,
        )
        expected_apps.add(provider_app)

        # remove provider.in_relations
        to_delete = [
            _prepare_relation(relation, model, add=False)
            for relation in provider.in_relations
        ]

        # add provider.out_relations
        to_add = [
            _prepare_relation(relation, model, add=True)
            for relation in provider.out_relations
        ]
        await asyncio.gather(*to_add + to_delete)
    elif not out_of_tree and provider_deployed:
        logger.info(f"Removing Provider={provider_app} from model.")
        expected_apps.remove(provider_app)

        # remove provider.out_relations
        to_delete = [
            _prepare_relation(relation, model, add=False)
            for relation in provider.out_relations
        ]

        # add provider.in_relations
        to_add = [
            _prepare_relation(relation, model, add=True)
            for relation in provider.in_relations
        ]
        await asyncio.gather(*to_add + to_delete)

        # remove provider.application
        await model.applications[provider_app].remove()

    logger.info(f"Waiting for stable apps=[{', '.join(expected_apps)}].")
    await model.wait_for_idle(apps=expected_apps, wait_for_active=True, timeout=15 * 60)
    if not out_of_tree:
        logger.info("Installing Storage Class from template.")
        storage_yml = TEMPLATE_PATH / cloud / "storage-class.yaml"
        await kubectl_apply(storage_yml, model)
        yield yaml.safe_load(storage_yml.read_text())["metadata"]["name"]
        logger.info("Removing Storage Class from template.")
        await kubectl_delete(storage_yml, model)

    else:
        logger.info(f"Using provider storage class {provider.storage_class}.")
        yield provider.storage_class


@pytest.fixture(scope="function")
async def storage_pvc(model, storage_class, tmp_path):
    """Sets up and tearsdown k8s resources"""

    pv_claim_yml = TEMPLATE_PATH / "pv-claim.yaml"
    template = jinja2.Template(pv_claim_yml.read_text())
    rendered = tmp_path / "pv-claim.yaml"
    rendered.write_text(template.render(storage_class=storage_class))

    logger.info(f"Installing PVC from template with sc={storage_class}.")
    await kubectl_apply(rendered, model)
    yield yaml.safe_load(rendered.read_text())["metadata"]["name"]

    logger.info(f"Removing PVC from template with sc={storage_class}.")
    await kubectl_delete(rendered, model)


@retry(tries=4, delay=15, logger=logger)
def wait_for(resource: str, matcher: Tuple[str, Any], kubeconfig=None, **kwargs):
    def lookup(rsc, keys):
        head, *tail = keys.split(".", 1)
        return lookup(rsc[head], tail[0]) if tail else rsc[head]

    key, final_status = matcher
    kubectl = sh.kubectl
    if kubeconfig:
        kubectl = sh.kubectl.bake("--kubeconfig", kubeconfig)

    out = kubectl.get(resource, **kwargs)
    rsc_list = yaml.safe_load(out.stdout.decode("utf-8"))
    status, *_ = [lookup(rsc, key) for rsc in rsc_list["items"]]
    if status != final_status:
        raise Exception(f"Resource {resource}[{key}] is {status} not {final_status}")


async def test_storage(request, model, storage_pvc, tmp_path, kubeconfig):
    pv_test_yaml = TEMPLATE_PATH / "pv-test.yaml"
    test_name = request.node.name.replace("[", "-").replace("]", "")
    template = jinja2.Template(pv_test_yaml.read_text())
    rendered = tmp_path / "pv-test.yaml"
    rendered.write_text(template.render(storage_pvc=storage_pvc, test_name=test_name))
    welcome = "Hello from Charmed Kubernetes"
    nginx_path = "/usr/share/nginx/html"

    logger.info(f"Starting NGINX with pvc={storage_pvc}.")
    await kubectl_apply(rendered, model)
    try:
        wait_for(
            "pod",
            ("status.phase", "Running"),
            o="yaml",
            selector=f"test-name={test_name}",
            kubeconfig=kubeconfig,
        )
        pod_exec = sh.kubectl.bake(
            "--kubeconfig", kubeconfig, "exec", "-it", "task-pv-pod", "--"
        )

        # Ensure the PV is mounted
        out = pod_exec("mount")
        mount_points = out.stdout.decode("utf-8").splitlines()
        assert any(nginx_path in mount for mount in mount_points), "PV Mount not found"

        # Ensure the PV is writable
        write_index_html = f"echo -e '{welcome}' > {nginx_path}/index.html"
        pod_exec("bash", "-c", write_index_html)

        # Ensure the PV is readable by the application
        pod_exec("apt", "update")
        pod_exec("apt", "install", "curl")
        out = pod_exec("curl", "http://localhost/")
        assert welcome in out.stdout.decode("utf-8")
    finally:
        logger.info(f"Terminating NGINX with pvc={storage_pvc}.")
        await kubectl_delete(rendered, model)


@retry(tries=12, delay=15, logger=logger)  # 3min
def retried(get, url):
    return get(url)


@pytest.mark.clouds(["ec2", "gce", "azure"])
async def test_load_balancer(tools, model, kubeconfig):
    """Performs a deployment of hello-world with newly created LB and attempts
    to do a fetch and parse the html to verify the lb ip address is
    functioning appropriately.
    """
    kubectl = sh.kubectl.bake("--kubeconfig", kubeconfig)
    lb_yaml = TEMPLATE_PATH / "lb-test.yaml"
    logger.info("Starting hello-world on port=8080.")
    await kubectl_apply(lb_yaml, model)
    try:
        wait_for(
            "deployment",
            ("status.availableReplicas", 5),
            o="yaml",
            selector="run=load-balancer-example",
            kubeconfig=kubeconfig,
        )
        out = kubectl.get("svc", o="yaml", selector="run=load-balancer-example")
        services = yaml.safe_load(out.stdout.decode("utf8"))
        (svc,) = services["items"]
        for key in ["ip", "hostname"]:
            if lb_ip := svc["status"]["loadBalancer"]["ingress"][0].get(key):
                break
        assert lb_ip, "Cannot find an active loadbalancer."
        html = retried(tools.requests.get, f"http://{lb_ip}:8080")
        assert "Hello Kubernetes!" in html.content.decode("utf-8")
    finally:
        logger.info("Terminating hello-world on port=8080.")
        await kubectl_delete(lb_yaml, model)
