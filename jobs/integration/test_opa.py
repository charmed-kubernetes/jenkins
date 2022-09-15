import asyncio
import json
import random
from pathlib import Path

from juju.utils import block_until_with_coroutine
import pytest

from .logger import log
from .utils import (
    JujuRunError,
    kubectl,
    scp_to,
    wait_for_application_status,
    kubectl_apply,
    kubectl_delete,
)

templates = Path(__file__).parent / "templates"


class OPATestBase:
    @pytest.fixture(autouse=True)
    def setup(self, model, k8s_model, tools):
        self.model = model
        self.k8s_model = k8s_model
        self.tools = tools
        control_plane_app = self.model.applications["kubernetes-control-plane"]
        self.control_plane_unit = control_plane_app.units[0]

    async def validate_create_ns_with_label(self):
        # Create the namespace
        log("Creating namespace")
        await kubectl_apply(
            templates / "validate-gatekeeper-policy.yaml",
            self.control_plane_unit,
            self.tools,
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
            self.control_plane_unit,
            self.tools,
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
        try:
            await kubectl(self.model, cmd)
        except JujuRunError as e:
            err = e.output
            if err.startswith(
                "Error from server (InternalError): Internal error occurred"
            ):
                # Try again as it might be transient/initialization related
                await asyncio.sleep(10)
                try:
                    await kubectl(self.model, cmd)
                except JujuRunError as e:
                    err = e.output
                else:
                    pytest.fail("Creating the namespace should fail, but it didn't")
        else:
            pytest.fail("Creating the namespace should fail, but it didn't")
        assert err.startswith(
            "Error from server (Forbidden): admission webhook "
            '"validation.gatekeeper.sh" denied the request:'
        )

    async def deploy_example_policy(self):
        await kubectl_apply(
            templates / "gatekeeper-policy.yaml",
            self.control_plane_unit,
            self.tools,
            self.model,
        )
        await kubectl_apply(
            templates / "gatekeeper-policy-spec.yaml",
            self.control_plane_unit,
            self.tools,
            self.model,
        )

    async def destroy_example_policy(self):
        log("Delete example policy")
        await kubectl_delete(
            templates / "gatekeeper-policy.yaml",
            self.control_plane_unit,
            self.tools,
            self.model,
        )

    @pytest.fixture(scope="class")
    async def storage_class(self, model, k8s_model, tools):
        control_plane_app = model.applications["kubernetes-control-plane"]
        control_plane_unit = control_plane_app.units[0]
        try:
            await kubectl_apply(
                templates / "integrator-charm-data" / "vsphere" / "storage-class.yaml",
                control_plane_unit,
                tools,
                model,
            )
            yield
        finally:
            await kubectl_delete(
                templates / "integrator-charm-data" / "vsphere" / "storage-class.yaml",
                control_plane_unit,
                tools,
                model,
            )

    @pytest.fixture(scope="class")
    async def storage_pool(self, model, k8s_model, tools, storage_class):
        storage_pool_name = "teststorage"
        log("Creating storage pool")
        try:
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
            await tools.run(
                "juju",
                "remove-storage-pool",
                "-m",
                tools.k8s_connection,
                storage_pool_name,
            )

    @pytest.fixture(scope="class")
    async def update_status_interval(self, tools, k8s_model):
        interval = await tools.run(
            "juju",
            "model-config",
            "-m",
            tools.k8s_connection,
            "update-status-hook-interval",
        )
        interval = interval[0].strip()
        try:
            log("Decrease update status hook interval")
            await tools.run(
                "juju",
                "model-config",
                "-m",
                tools.k8s_connection,
                "update-status-hook-interval=5s",
            )
            yield
        finally:
            await tools.run(
                "juju",
                "model-config",
                "-m",
                tools.k8s_connection,
                f"update-status-hook-interval={interval}",
            )

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
            await tools.run(
                "juju",
                "remove-application",
                "-m",
                tools.k8s_connection,
                "--force",
                "gatekeeper-controller-manager",
            )
            await self.wait_for_app_removed("gatekeeper-controller-manager", k8s_model)

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
            await tools.run(
                "juju",
                "remove-application",
                "-m",
                tools.k8s_connection,
                "--force",
                "--destroy-storage",
                "gatekeeper-audit",
            )
            await self.wait_for_app_removed("gatekeeper-audit", k8s_model)

    async def _validate_audit_actions(self, unit):
        log("Running list-violations action")
        total_violations = 0
        while total_violations == 0:
            action = await unit.run_action("list-violations")
            await action.wait()
            assert action.status == "completed"
            assert "constraint-violations" in action.results
            constraint_violations = json.loads(action.results["constraint-violations"])
            if constraint_violations:
                total_violations = constraint_violations[0].get("total-violations")
            await asyncio.sleep(5)

        log("Running get-violation action")
        action = await unit.run_action(
            "get-violation",
            **{
                "constraint-template": "K8sRequiredLabels",
                "constraint": "ns-must-have-gk",
            },
        )
        await action.wait()
        assert len(json.loads(action.results["violations"])) > 0

    async def wait_for_units(
        self, app, error_status=("blocked", "error"), expected_status="active"
    ):
        while (
            status := app.units[0].workload_status if app.units else None
        ) != expected_status:
            assert status not in error_status
            await asyncio.sleep(5)

    async def wait_for_app_removed(self, app_name, k8s_model=None):
        if not k8s_model:
            k8s_model = self.k8s_model

        async def check_app_missing():
            apps = await k8s_model.get_status()
            return app_name not in apps.applications

        try:
            await block_until_with_coroutine(check_app_missing, timeout=120)
        except asyncio.TimeoutError as e:
            raise AssertionError(f"Application {app_name} was not removed")


@pytest.mark.clouds(["vsphere"])
class TestOPAWebhook(OPATestBase):
    async def test_opa_webhook_ready(self, opa_controller_manager):
        await self.wait_for_units(opa_controller_manager)
        unit = opa_controller_manager.units[0]

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
            await self.wait_for_units(audit)

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
            await self.tools.run(
                "juju",
                "remove-application",
                "-m",
                self.tools.k8s_connection,
                "--force",
                "--destroy-storage",
                "gatekeeper-audit",
            )
            await self.wait_for_app_removed("gatekeeper-audit")

    async def test_manager_reconcile(
        self, opa_controller_manager, update_status_interval
    ):
        await self.wait_for_units(
            opa_controller_manager, error_status=("error",), expected_status="blocked"
        )
        log("Reconcile resources")
        await opa_controller_manager.units[0].run_action("reconcile-resources")
        await self.wait_for_units(opa_controller_manager, error_status=("error",))

        # Check that the opa_controller_manager works
        await self.validate_create_ns()
        log("Creating policy and constraint crds")
        await self.deploy_example_policy()
        log("Test that the policy is enforced")
        await self.validate_create_ns_fail()
        await self.validate_create_ns_with_label()
        await self.destroy_example_policy()


@pytest.mark.clouds(["vsphere"])
class TestOPAAudit(OPATestBase):
    async def test_opa_audit_ready(self, opa_audit):
        await self.wait_for_units(opa_audit)

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

    @pytest.mark.dependency()
    async def test_manager_deploy(self, opa_audit, update_status_interval):
        log("Deploying the gatekeeper charm")
        webhook = await self.k8s_model.deploy(
            "gatekeeper-controller-manager",
            channel=self.tools.charm_channel,
            trust=True,
        )
        try:
            await self.wait_for_units(webhook)
            await wait_for_application_status(
                self.k8s_model, "gatekeeper-controller-manager", status="active"
            )

            log("Test that the policy is enforced")
            await self.validate_create_ns_fail()
            await self.validate_create_ns_with_label()
        finally:
            log("Deleting the gatekeeper charm")
            await webhook.destroy()
            await self.wait_for_app_removed("gatekeeper-controller-manager")

    @pytest.mark.dependency(depends=["test_manager_deploy"])
    async def test_audit_reconcile(self, opa_audit, update_status_interval):
        log("Waiting for status to change to blocked")
        await self.wait_for_units(
            opa_audit, error_status=("error",), expected_status="blocked"
        )
        log("Reconcile resources")
        await opa_audit.units[0].run_action("reconcile-resources")
        await self.wait_for_units(opa_audit, error_status=("error",))

        log("Creating policy and constraint crds")
        await self.deploy_example_policy()
        await self._validate_audit_actions(opa_audit.units[0])
