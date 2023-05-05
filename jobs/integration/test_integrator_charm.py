import asyncio
import logging
from colorama import Fore
from dataclasses import dataclass, field
from enum import Enum, auto
from juju.errors import JujuError
from pathlib import Path
import os
import random
import re
import sh
import pytest
from typing import Any, Callable, List, Mapping, Tuple
import yaml

import jinja2
from retry import retry

from jobs.integration.conftest import Tools

from .utils import juju_run_retry, kubectl_apply, kubectl_delete

env = os.environ.copy()
logger = logging.getLogger(__name__)


class Tree(Enum):
    IN_TREE = auto()
    OUT_OF_TREE = auto()


@dataclass
class Provider:
    application: str
    out_relations: List[Tuple[str, str]] = field(default_factory=lambda: [])
    in_relations: List[Tuple[str, str]] = field(default_factory=lambda: [])
    config: Mapping[str, str] = field(default_factory=dict)
    channel: str = "edge"
    in_tree_until: str = None
    trust: bool = False


@dataclass
class OutOfTreeConfig:
    storage_class: str
    storage: Provider
    cloud_controller: Provider

    @classmethod
    def from_dict(cls, kw):
        ccm, stor = kw.pop("cloud_controller"), kw.pop("storage")
        ccm = Provider(**{k.replace("-", "_"): ccm[k] for k in ccm})
        stor = Provider(**{k.replace("-", "_"): stor[k] for k in stor})
        return cls(storage=stor, cloud_controller=ccm, **kw)


@dataclass
class LoadBalancerConfig:
    service_endpoint: str


TEMPLATE_PATH = Path(__file__).absolute().parent / "templates/integrator-charm-data"


def _prepare_relation(linkage, model, add=True):
    left, right = linkage
    left_app, left_relation = left.split(":")
    right_app, *_ = right.split(":")
    for app in (left_app, right_app):
        if app not in model.applications:
            if add:
                raise JujuError(f"{app} cannot be related -- not deployed")
            else:
                logger.info(f"{app} doesn't exist, already unrelated")
                return asyncio.sleep(0)

    # removing a relation when the application isn't deployed isn't necessary
    app = model.applications[left_app]
    right_endpoints = [
        endpoint
        for rel in app.relations
        if left in str(rel)
        for endpoint in rel.endpoints
        if left not in str(endpoint)
    ]
    exists = any(right in str(_) for _ in right_endpoints)
    if add and not exists:
        return app.relate(left_relation, right)
    elif not add and exists:
        return app.destroy_relation(left_relation, right)
    return asyncio.sleep(0)


def out_of_tree_config(cloud):
    provider_file = TEMPLATE_PATH / cloud / "out-of-tree.yaml"
    config = yaml.safe_load(provider_file.read_text())
    return OutOfTreeConfig.from_dict({k.replace("-", "_"): config[k] for k in config})


def loadbalancer_config(cloud):
    provider_file = TEMPLATE_PATH / cloud / "load-balancer.yaml"
    config = yaml.safe_load(provider_file.read_text())
    return LoadBalancerConfig(**{k.replace("-", "_"): config[k] for k in config})


async def _add_provider(model, provider: Provider):
    provider_app = provider.application

    if provider_app and provider_app not in model.applications:
        logger.info(f"Adding provider={provider_app} to model.")
        # deploy provider.application
        await model.deploy(
            provider_app,
            channel=provider.channel,
            trust=provider.trust,
            config=provider.config,
        )

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


async def _remove_provider(model, provider: Provider):
    provider_app = provider.application

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

    if provider_app and provider_app in model.applications:
        logger.info(f"Removing Provider={provider_app} from model.")
        # remove provider.application
        await model.applications[provider_app].remove()


async def _resolve_provider(model, provider, tools, version, expected_apps):
    in_tree_version = tuple(int(i) for i in provider.in_tree_until.split(".")[:2])
    if version > in_tree_version:
        method = _add_provider
        if provider.application:
            expected_apps.add(provider.application)
    else:
        method = _remove_provider
        if provider.application:
            expected_apps.discard(provider.application)
    provider.channel = tools.charm_channel
    await method(model, provider)


@pytest.fixture(scope="module")
async def kubernetes_version(model):
    worker_app = model.applications["kubernetes-worker"]
    k8s_version_str = worker_app.data["workload-version"]
    return tuple(int(i) for i in k8s_version_str.split(".")[:2])


@pytest.fixture(scope="module")
async def cloud_providers(tools: Tools, model, cloud, kubernetes_version):
    out_of_tree = out_of_tree_config(cloud)
    expected_apps = set(model.applications)
    for provider in (out_of_tree.storage, out_of_tree.cloud_controller):
        await _resolve_provider(
            model, provider, tools, kubernetes_version, expected_apps
        )

    logger.info(f"Waiting for stable apps=[{', '.join(expected_apps)}].")
    await model.wait_for_idle(
        apps=list(expected_apps), wait_for_active=True, timeout=15 * 60
    )


@pytest.fixture(scope="module")
async def storage_class(cloud_providers, model, cloud, kubernetes_version):
    out_of_tree = out_of_tree_config(cloud)
    support_version = tuple(
        int(i) for i in out_of_tree.storage.in_tree_until.split(".")[:2]
    )

    if kubernetes_version <= support_version:
        logger.info("Installing Storage Class from template.")
        storage_yml = TEMPLATE_PATH / cloud / "storage-class.yaml"
        await kubectl_apply(storage_yml, model)
        yield yaml.safe_load(storage_yml.read_text())["metadata"]["name"]
        logger.info("Removing Storage Class from template.")
        await kubectl_delete(storage_yml, model)
    else:
        logger.info(f"Using cloud storage class {out_of_tree.storage_class}.")
        yield out_of_tree.storage_class


@pytest.fixture(scope="function")
async def storage_pvc(model, storage_class, tmp_path):
    """Sets up and tearsdown k8s pvc resources"""

    pv_claim_yml = TEMPLATE_PATH / "pv-claim.yaml"
    template = jinja2.Template(pv_claim_yml.read_text())
    rendered = tmp_path / "pv-claim.yaml"
    rendered.write_text(template.render(storage_class=storage_class))

    logger.info(f"Installing PVC from template with sc={storage_class}.")
    await kubectl_apply(rendered, model)
    yield yaml.safe_load(rendered.read_text())["metadata"]["name"]

    logger.info(f"Removing PVC from template with sc={storage_class}.")
    await kubectl_delete(rendered, model)


KeyMatcher = Tuple[str, Callable[[Any], bool]]


@retry(tries=5, delay=15, backoff=2, logger=logger)
def wait_for(resource: str, key_matcher: KeyMatcher, kubeconfig=None, **kwargs):
    l_index_re = re.compile(r"^(\w+)\[(\d+)\]$")

    def lookup(rsc, keys):
        head, *tail = keys.split(".", 1)
        key_and_index = l_index_re.findall(head)
        if not key_and_index:
            return lookup(rsc[head], tail[0]) if tail else rsc[head]
        key, index = key_and_index[0]
        dereference = rsc[key][int(index)]
        return lookup(dereference, tail[0]) if tail else dereference

    key, matcher = key_matcher
    kubectl = sh.kubectl
    if kubeconfig:
        kubectl = sh.kubectl.bake("--kubeconfig", kubeconfig)

    out = kubectl.get(resource, **kwargs)
    rsc_list = yaml.safe_load(out)
    status, *_ = [lookup(rsc, key) for rsc in rsc_list["items"]]
    if not matcher(status):
        raise Exception(f"Resource {resource}[{key}] is {status} and doesn't match")
    return status


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
    kubectl = sh.kubectl.bake("--kubeconfig", kubeconfig)
    try:
        wait_for(
            "pod",
            ("status.phase", lambda s: s == "Running"),
            o="yaml",
            selector=f"test-name={test_name}",
            kubeconfig=kubeconfig,
        )
        pod_exec = kubectl.bake(
            "exec",
            "-it",
            "task-pv-pod",
            "--",
            _tee=True,
            _out=lambda _: logger.info(Fore.CYAN + _.strip() + Fore.RESET),
            _err=lambda _: logger.warning(Fore.YELLOW + _.strip() + Fore.RESET),
        )

        # Ensure the PV is mounted
        out = pod_exec("mount")
        mount_points = out.splitlines()
        assert any(nginx_path in mount for mount in mount_points), "PV Mount not found"

        # Ensure the PV is writable
        write_index_html = f"echo -e '{welcome}' > {nginx_path}/index.html"
        pod_exec("bash", "-c", write_index_html)

        # Ensure the PV is readable by the application
        out = pod_exec("curl", "http://localhost/")
        assert welcome in out
    finally:
        events = kubectl.get.event(
            "--field-selector", "involvedObject.name=task-pv-pod"
        )
        logger.info(f"NGINX POD events:\n{events}")
        logger.info(f"Terminating NGINX with pvc={storage_pvc}.")
        await kubectl_delete(rendered, model)


@pytest.mark.clouds(["ec2", "gce", "azure"])
@pytest.mark.usefixtures("cloud_providers")
async def test_load_balancer(model, cloud, kubeconfig):
    """Performs a deployment of hello-world with newly created LB and attempts
    to do a fetch and parse the html to verify the lb ip address is
    functioning appropriately.
    """
    lb_config = loadbalancer_config(cloud)
    lb_yaml = TEMPLATE_PATH / "lb-test.yaml"
    logger.info("Starting hello-world on port=8080.")

    control_plane = model.applications["kubernetes-control-plane"]
    control_plane_unit = random.choice(control_plane.units)

    await kubectl_apply(lb_yaml, model)
    try:
        wait_for(
            "deployment",
            ("status.availableReplicas", lambda r: r == 5),
            o="yaml",
            selector="run=load-balancer-example",
            kubeconfig=kubeconfig,
        )
        lb_endpoint = wait_for(
            "service",
            (
                f"status.loadBalancer.ingress[0].{lb_config.service_endpoint}",
                lambda i: i,  # value just needs to be truthy (should be an ip or hostname)
            ),
            o="yaml",
            selector="run=load-balancer-example",
            kubeconfig=kubeconfig,
        )
        assert lb_endpoint, "Cannot find an active loadbalancer."
        result = await juju_run_retry(
            control_plane_unit, f"curl -s http://{lb_endpoint}:8080", tries=12, delay=15
        )
        assert "Hello Kubernetes!" in result.output
    finally:
        logger.info("Terminating hello-world on port=8080.")
        await kubectl_delete(lb_yaml, model)
