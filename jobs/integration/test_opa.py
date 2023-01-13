import asyncio
import json
import random
from pathlib import Path

import pytest

from .logger import log
from .utils import (
    JujuRunError,
    kubectl,
    wait_for_application_status,
    kubectl_apply,
    kubectl_delete,
    juju_run_action,
)

templates = Path(__file__).parent / "templates"


@pytest.mark.clouds(["vsphere"])
class OPATestBase:
    @pytest.fixture(autouse=True)
    def setup(self, model, k8s_model, tools):
        self.model = model
        self.k8s_model = k8s_model
        self.tools = tools

    async def validate_create_ns_with_label(self):
        # Create the namespace
        log("Creating namespace")
        await kubectl_apply(
            templates / "validate-gatekeeper-policy.yaml",
            self.model,
        )

        # Wait for namespace to go active
        cmd = "get ns test-ns -o jsonpath='{.status.phase}'"
        log("Waiting for namespace to become active")
        while result := await kubectl(self.model, cmd):
            if result.output == "Active":
                break
            await asyncio.sleep(1)

        # Delete the namespace
        cmd = "delete ns test-ns"
        await kubectl_delete(
            templates / "validate-gatekeeper-policy.yaml",
            self.model,
        )

    async def validate_create_ns(self, name=None):
        if not name:
            name = f"test-ns-{random.randint(1, 99999)}"

        cmd = f"create ns {name}"
        log("Creating namespace without any labels")
        await kubectl(self.model, cmd)

        # Wait for namespace to go active
        cmd = f"get ns {name} -o jsonpath='{{.status.phase}}'"
        log("Waiting for namespace to become active")
        while result := await kubectl(self.model, cmd):
            if result.output == "Active":
                break
            await asyncio.sleep(1)

        # Delete the namespace
        cmd = f"delete ns {name}"
        await kubectl(self.model, cmd)

    async def validate_create_ns_fail(self, name=None):
        if not name:
            name = f"test-ns-{random.randint(1, 99999)}"

        cmd = f"create ns {name}"
        # Creating the namespace should raise
        log("Creating namespace without any labels")
        with pytest.raises(JujuRunError, match="Forbidden|InternalError") as exc_info:
            await kubectl(self.model, cmd)

        if "InternalError" in str(exc_info.value):
            await asyncio.sleep(10)
            # Try again as it might be transient/initialization related
            with pytest.raises(JujuRunError, match="Forbidden") as exc_info:
                await kubectl(self.model, cmd)

        assert exc_info.value.output.startswith(
            "Error from server (Forbidden): admission webhook "
            '"validation.gatekeeper.sh" denied the request:'
        )

    async def deploy_example_policy(self):
        await kubectl_apply(
            templates / "gatekeeper-policy.yaml",
            self.model,
        )
        await kubectl_apply(
            templates / "gatekeeper-policy-spec.yaml",
            self.model,
        )

    async def destroy_example_policy(self):
        log("Delete example policy")
        await kubectl_delete(
            templates / "gatekeeper-policy.yaml",
            self.model,
        )

    @pytest.fixture(scope="class")
    async def storage_class(self, model, k8s_model):
        try:
            await kubectl_apply(
                templates / "integrator-charm-data" / "vsphere" / "storage-class.yaml",
                model,
            )
            yield
        finally:
            await kubectl_delete(
                templates / "integrator-charm-data" / "vsphere" / "storage-class.yaml",
                model,
            )

    @pytest.fixture(scope="class")
    async def storage_pool(self, model, k8s_model, tools, storage_class):
        storage_pool_name = "teststorage"
        log("Creating storage pool")
        try:
            # TODO: When use `k8s_model.create_storage_pool` once we start using
            # python-libjuju  >= 3.0.0
            await tools.run(
                "juju",
                "create-storage-pool",
                storage_pool_name,
                "kubernetes",
                "-m",
                tools.k8s_connection,
                "storage-class=mystorage",
            )
            yield storage_pool_name
        finally:
            log("Removing storage pool")
            # TODO: When use `k8s_model.remove_storage_pool` once we start using
            # python-libjuju  >= 3.0.0
            await tools.run(
                "juju",
                "remove-storage-pool",
                "-m",
                tools.k8s_connection,
                storage_pool_name,
            )

    @pytest.fixture(scope="class")
    async def update_status_interval(self, tools, k8s_model):
        model_config = await k8s_model.get_config()
        interval = model_config.get("update-status-hook-interval").value
        try:
            log("Decrease update status hook interval")
            await k8s_model.set_config({"update-status-hook-interval": "5s"})
            yield
        finally:
            await k8s_model.set_config({"update-status-hook-interval": interval})

    @pytest.fixture(scope="class")
    async def opa_controller_manager(self, model, k8s_model, tools):
        try:
            log("Deploying the webhook charm")
            webhook = await k8s_model.deploy(
                "gatekeeper-controller-manager",
                channel=tools.charm_channel,
                trust=True,
            )
            yield webhook
        finally:
            log("Deleting the gatekeeper charm")
            await k8s_model.remove_application(webhook.name)
            await tools.juju_wait(m=tools.k8s_connection, max_wait=120)

    @pytest.fixture(scope="class")
    async def opa_audit(self, model, k8s_model, tools, storage_pool):
        try:
            log("Deploying the audit charm")
            audit = await k8s_model.deploy(
                "gatekeeper-audit",
                channel=tools.charm_channel,
                trust=True,
                storage={"audit-volume": {"pool": storage_pool}},
                config={"audit-interval": 1},
            )
            yield audit
        finally:
            log("Deleting the audit charm")
            # TODO: Currently `k8s_model.remove_application` does not support removing
            # storage, this feature will be added in a later python-libjuju version,
            # once that is done we should replace this with one such call.
            await tools.run(
                "juju",
                "remove-application",
                "-m",
                tools.k8s_connection,
                "--force",
                "--destroy-storage",
                "gatekeeper-audit",
            )
            await tools.juju_wait(m=tools.k8s_connection, max_wait=120)

    async def _validate_audit_actions(self, unit):
        log("Running list-violations action")
        total_violations = 0
        while total_violations == 0:
            action = await juju_run_action(unit, "list-violations")
            assert action.status == "completed"
            assert "constraint-violations" in action.results
            constraint_violations = json.loads(action.results["constraint-violations"])
            if constraint_violations:
                total_violations = constraint_violations[0].get("total-violations")
            await asyncio.sleep(5)

        log("Running get-violation action")
        action = await juju_run_action(
            unit,
            "get-violation",
            **{
                "constraint-template": "K8sRequiredLabels",
                "constraint": "ns-must-have-gk",
            },
        )
        assert len(json.loads(action.results["violations"])) > 0

    async def wait_for_units(
        self, app, error_status=("blocked", "error"), expected_status="active"
    ):
        while (
            status := app.units[0].workload_status if app.units else None
        ) != expected_status:
            assert status not in error_status
            await asyncio.sleep(5)


class TestOPAWebhook(OPATestBase):
    async def test_opa_webhook_ready(self, opa_controller_manager):
        await self.tools.juju_wait(m=self.tools.k8s_connection, max_wait=120)

        log("Waiting for gatekeeper charm to be ready")
        await wait_for_application_status(
            self.k8s_model, "gatekeeper-controller-manager", status="active"
        )

    async def test_create_ns_no_policy(self, opa_controller_manager):
        try:
            await self.validate_create_ns()
        except JujuRunError as e:
            if e.output.startswith(
                "Error from server (InternalError): Internal error occurred"
            ):
                # Try again as it might be transient/initialization related
                await asyncio.sleep(5)
                await self.validate_create_ns()
            else:
                raise

    async def test_policy_enforcement(self, opa_controller_manager):
        log("Creating policy and constraint crds")
        await self.deploy_example_policy()
        log("Test that the policy is enforced")
        try:
            await self.validate_create_ns_fail()
            await self.validate_create_ns_with_label()
        finally:
            await self.destroy_example_policy()

    async def test_audit_deploy(
        self, opa_controller_manager, update_status_interval, storage_pool
    ):
        log("Deploying the audit charm")
        audit = await self.k8s_model.deploy(
            "gatekeeper-audit",
            channel=self.tools.charm_channel,
            trust=True,
            storage={"audit-volume": {"pool": storage_pool}},
            config={"audit-interval": 1},
        )

        log("Waiting for audit charm to be ready")
        try:
            await self.tools.juju_wait(m=self.tools.k8s_connection, max_wait=120)
            await wait_for_application_status(
                self.k8s_model, "gatekeeper-audit", status="active"
            )

            await self.deploy_example_policy()
            log("Test that the policy is enforced")
            await self.validate_create_ns_fail()
            await self.validate_create_ns_with_label()
            await self._validate_audit_actions(audit.units[0])
            await self.destroy_example_policy()
            log("Validate that the policy is no longer enforced")
            await self.validate_create_ns()
        finally:
            log("Deleting the audit charm")
            # TODO: Currently `k8s_model.remove_application` does not support removing
            # storage, this feature will be added in a later python-libjuju version,
            # once that is done we should replace this with one such call.
            await self.tools.run(
                "juju",
                "remove-application",
                "-m",
                self.tools.k8s_connection,
                "--force",
                "--destroy-storage",
                "gatekeeper-audit",
            )
            await self.tools.juju_wait(m=self.tools.k8s_connection, max_wait=120)

    async def test_manager_reconcile(
        self, opa_controller_manager, update_status_interval
    ):
        await self.wait_for_units(
            opa_controller_manager, error_status=("error",), expected_status="blocked"
        )
        log("Reconcile resources")
        await juju_run_action(opa_controller_manager.units[0], "reconcile-resources")
        await self.tools.juju_wait(m=self.tools.k8s_connection, max_wait=120)

        # Check that the opa_controller_manager works
        await self.validate_create_ns()
        log("Creating policy and constraint crds")
        await self.deploy_example_policy()
        log("Test that the policy is enforced")
        await self.validate_create_ns_fail()
        await self.validate_create_ns_with_label()
        await self.destroy_example_policy()


class TestOPAAudit(OPATestBase):
    async def test_opa_audit_ready(self, opa_audit):
        await self.tools.juju_wait(m=self.tools.k8s_connection, max_wait=120)

        log("Waiting for audit charm to be ready")
        await wait_for_application_status(
            self.k8s_model, "gatekeeper-audit", status="active"
        )

    async def test_create_ns_no_policy(self, opa_audit):
        await self.validate_create_ns()

    async def test_policy_auditing(self, opa_audit, update_status_interval):
        log("Creating policy and constraint crds")
        await self.deploy_example_policy()
        await self._validate_audit_actions(opa_audit.units[0])

    async def test_manager_deploy(self, opa_audit, update_status_interval):
        log("Deploying the gatekeeper charm")
        webhook = await self.k8s_model.deploy(
            "gatekeeper-controller-manager",
            channel=self.tools.charm_channel,
            trust=True,
        )
        try:
            await self.tools.juju_wait(m=self.tools.k8s_connection, max_wait=120)
            await wait_for_application_status(
                self.k8s_model, "gatekeeper-controller-manager", status="active"
            )

            log("Test that the policy is enforced")
            await self.validate_create_ns_fail()
            await self.validate_create_ns_with_label()
        finally:
            log("Deleting the gatekeeper charm")
            await webhook.destroy()
            await self.tools.juju_wait(m=self.tools.k8s_connection, max_wait=120)

    async def test_audit_reconcile(self, opa_audit, update_status_interval):
        log("Waiting for status to change to blocked")
        await self.wait_for_units(
            opa_audit, error_status=("error",), expected_status="blocked"
        )
        log("Reconcile resources")
        await juju_run_action(opa_audit.units[0], "reconcile-resources")
        await self.tools.juju_wait(m=self.tools.k8s_connection, max_wait=120)

        log("Creating policy and constraint crds")
        await self.deploy_example_policy()
        await self._validate_audit_actions(opa_audit.units[0])
