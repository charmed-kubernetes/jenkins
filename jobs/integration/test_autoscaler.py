from datetime import datetime, timedelta
import logging
import pytest
import random
import re
import string
from pathlib import Path
from typing import Optional


parent = Path(__file__).parent
log = logging.getLogger(__name__)


@pytest.fixture(scope="module")
def module_name(request):
    return re.sub(r"[._]", "-", request.module.__name__)


@pytest.fixture(scope="module")
def namespace(module_name):
    rand_str = "".join(random.choices(string.ascii_lowercase + string.digits, k=5))
    yield f"{module_name}-{rand_str}"


@pytest.fixture(scope="module")
async def deployment(kubectl, namespace):
    path_to_deployment = parent / "templates" / "nginx_deployment.yaml"
    kubectl.create.namespace(namespace)
    kubectl.create(f=path_to_deployment, namespace=namespace)
    yield path_to_deployment
    kubectl.delete(f=path_to_deployment, namespace=namespace, grace_period=5 * 60)
    kubectl.delete.namespace(namespace)


@pytest.fixture
def scaled_up_deployment(kubectl, namespace, deployment):
    log.info("Scaling nginx deployment up to 115 units...")
    kubectl.scale(f=deployment, replicas=115, namespace=namespace)


@pytest.fixture
def scaled_down_deployment(kubectl, namespace, deployment):
    log.info("Scaling nginx deployment down to 0 units...")
    kubectl.scale(f=deployment, replicas=0, namespace=namespace)


async def wait_for_worker_count(model, expected_workers):
    """
    Blocks waiting for worker count within the model to reach the expected number.

    checks every half a second if the model has the required number of worker units.
    Logs a message every 30 seconds about the number of workers
    """
    last_log_time: Optional[datetime] = None
    log_interval = timedelta(seconds=30)

    def condition():
        nonlocal last_log_time
        unit_count = len(model.applications["kubernetes-worker"].units)
        if last_log_time is None or (datetime.now() - last_log_time) > log_interval:
            log.info(f"Worker count {unit_count} != {expected_workers}... ")
            last_log_time = datetime.now()
        elif unit_count == expected_workers:
            log.info(f"Worker count reached {unit_count}")
        return unit_count == expected_workers

    await model.block_until(condition, timeout=25 * 60)


async def test_scale_up(scaled_up_deployment, model):
    log.info("Watching workers expand...")
    assert len(model.applications["kubernetes-worker"].units) == 1
    await wait_for_worker_count(model, 2)
    await model.wait_for_idle(status="active", timeout=25 * 60)


async def test_scale_down(scaled_down_deployment, model):
    log.info("Watching workers contract...")
    assert len(model.applications["kubernetes-worker"].units) == 2
    await wait_for_worker_count(model, 1)
    await model.wait_for_idle(status="active", timeout=25 * 60)
