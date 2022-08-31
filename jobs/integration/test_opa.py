import asyncio
import json
import random
from pathlib import Path

import pytest

from .logger import log
from .utils import JujuRunError, kubectl, scp_to, wait_for_application_status

templates = Path(__file__).parent / "templates"


class TestOPA:
    @pytest.fixture(autouse=True)
    def setup(self, model, k8s_model, tools):
        self.model = model
        self.k8s_model = k8s_model
        self.tools = tools
        control_plane_app = self.model.applications["kubernetes-control-plane"]
        self.control_plane_unit = control_plane_app.units[0]

    async def validate_create_ns_with_label(self):
        remote_path = "/tmp/validate-gatekeeper-policy.yaml"
        await scp_to(
            templates / "validate-gatekeeper-policy.yaml",
            self.control_plane_unit,
            remote_path,
            self.tools.controller_name,
            self.tools.connection,
        )

        # Create the namespace
        cmd = f"apply -f {remote_path}"
        log("Creating namespace")
        await kubectl(self.model, cmd)

        # Wait for namespace to go active
        cmd = "get ns test-ns -o jsonpath='{{.status.phase}}'"
        log("Waiting for namespace to become active")
        while result := await kubectl(self.model, cmd):
            if result.output == "Active":
                break
            await asyncio.sleep(1)

        # Delete the namespace
        cmd = "delete ns test-ns"
        await kubectl(self.model, cmd)

    async def validate_create_ns(self, name=None):
        if not name:
            name = f"test-ns-{random.randint(1, 99999)}"

        cmd = f"create ns {name}"
        log("Creating namespace")
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
            assert e.output.startswith(
                "Error from server (Forbidden): admission webhook "
                '"validation.gatekeeper.sh" denied the request:'
            )
        else:
            pytest.fail("Creating the namespace should fail, but it didn't")

    async def deploy_example_policy(self):
        remote_policy_path = "/tmp/policy.yaml"
        remote_policy_spec_path = "/tmp/policy-spec.yaml"
        await scp_to(
            templates / "gatekeeper-policy.yaml",
            self.control_plane_unit,
            remote_policy_path,
            self.tools.controller_name,
            self.tools.connection,
        )
        await scp_to(
            templates / "gatekeeper-policy-spec.yaml",
            self.control_plane_unit,
            remote_policy_spec_path,
            self.tools.controller_name,
            self.tools.connection,
        )
        await kubectl(self.model, f"apply -f {remote_policy_path}")
        await kubectl(self.model, f"apply -f {remote_policy_spec_path}")

    async def destroy_example_policy(self):
        remote_path = "/tmp/policy.yaml"
        await scp_to(
            templates / "gatekeeper-policy.yaml",
            self.control_plane_unit,
            remote_path,
            self.tools.controller_name,
            self.tools.connection,
        )
        await kubectl(self.model, f"delete -f {remote_path}")

    @pytest.fixture
    async def create_storage_pool(self, model, tools):
        # This assumes that we are running on vsphere, should it be
        # extended to run on other clouds as well?
        control_plane_app = model.applications["kubernetes-control-plane"]
        control_plane_unit = control_plane_app.units[0]
        remote_path = "/tmp/storage-class.yaml"
        storage_pool_name = "teststorage"
        await scp_to(
            templates / "integrator-charm-data" / "vsphere" / "storage-class.yaml",
            control_plane_unit,
            remote_path,
            tools.controller_name,
            tools.connection,
        )
        log("Creating storage class")
        try:
            await kubectl(model, f"create -f {remote_path}")
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
            log("Removing storage class")
            await kubectl(model, f"delete -f {remote_path}")
            await tools.run(
                "juju",
                "remove-storage-pool",
                "-m",
                tools.k8s_connection,
                storage_pool_name,
            )

    async def test_opa_webhook(self):
        log("Deploying the gatekeeper charm")
        webhook = await self.k8s_model.deploy(
            "gatekeeper-controller-manager",
            channel=self.tools.charm_channel,
            trust=True,
        )

        while (
            status := webhook.units[0].workload_status if webhook.units else None
        ) != "active":
            assert status not in ("blocked", "error")
            await asyncio.sleep(5)
        unit = webhook.units[0]

        try:
            log("Waiting for gatekeeper charm to be ready")
            await wait_for_application_status(
                self.k8s_model, "gatekeeper-controller-manager", status="active"
            )

            await self.validate_create_ns()
            log("Creating policy and constraint crds")
            await self.deploy_example_policy()
            log("Test that the policy is enforced")
            await self.validate_create_ns_fail()
            await self.validate_create_ns_with_label()
            log("Delete the policy")

            log("Deploying the audit charm")
            audit = await self.k8s_model.deploy(
                "gatekeeper-audit",
                channel=self.tools.charm_channel,
                trust=True,
            )
            while (
                status := audit.units[0].workload_status if audit.units else None
            ) != "active":
                assert status not in ("blocked", "error")
                await asyncio.sleep(5)

            log("Test that the policy is enforced")
            await self.validate_create_ns_fail()
            await self.validate_create_ns_with_label()
            await self.destroy_example_policy()
            log("Validate that the policy is no longer enforced")
            await self.validate_create_ns()

            log("Configuring charm to lower audit interval")
            await self.tools.run(
                "juju",
                "config",
                "-m",
                self.tools.k8s_connection,
                "gatekeeper-audit",
                "audit-interval=1",
            )
            await wait_for_application_status(
                self.k8s_model, "gatekeeper-audit", status="active"
            )

            log("Running list-violations action")
            total_violations = 0
            while total_violations == 0:
                action = await unit.run_action("list-violations")
                await action.wait()
                assert action.status == "completed"
                assert "constraint-violations" in action.results
                constraint_violations = json.loads(
                    action.results["constraint-violations"]
                )
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

            await audit.destroy()
            interval = await self.tools.run(
                "juju", "model-config", "update-status-hook-interval"
            )
            interval = interval[0].strip()
            try:
                log("Decrease update status hook interval")
                await self.tools.run(
                    "juju", "model-config", "update-status-hook-interval=5s"
                )
                log("Waiting for status to change to blocked")
                while (
                    status := webhook.units[0].workload_status
                    if webhook.units
                    else None
                ) != "blocked":
                    assert status != "error"
                    await asyncio.sleep(5)
                log("Reconcile resources")
                await unit.run_action("reconcile-resources")
                while (
                    status := webhook.units[0].workload_status
                    if webhook.units
                    else None
                ) != "active":
                    assert status != "error"
                    await asyncio.sleep(5)
            finally:
                await self.tools.run(
                    "juju", "model-config", f"update-status-hook-interval={interval}"
                )

            # Check that the webhook works
            await self.validate_create_ns()
            log("Creating policy and constraint crds")
            await self.deploy_example_policy()
            log("Test that the policy is enforced")
            await self.validate_create_ns_fail()
            await self.validate_create_ns_with_label()
            await self.destroy_example_policy()
        finally:
            log("Deleting the gatekeeper charm")
            await self.tools.run(
                "juju",
                "remove-application",
                "-m",
                self.tools.k8s_connection,
                "--force",
                "gatekeeper-controller-manager",
            )

    async def test_opa_audit(self, create_storage_pool):
        log("Deploying the gatekeeper charm")
        audit = await self.k8s_model.deploy(
            "gatekeeper-audit",
            channel=self.tools.charm_channel,
            trust=True,
            storage={"audit-volume": {"pool": create_storage_pool}},
        )
        while (
            status := audit.units[0].workload_status if audit.units else None
        ) != "active":
            assert status not in ("blocked", "error")
            await asyncio.sleep(5)

        unit = audit.units[0]

        log("Waiting for gatekeeper charm to be ready")
        await wait_for_application_status(
            self.k8s_model, "gatekeeper-audit", status="active"
        )
        await self.validate_create_ns()
        log("Creating policy and constraint crds")
        await self.deploy_example_policy()
        log("Configuring charm to lower audit interval")
        await self.tools.run(
            "juju",
            "config",
            "-m",
            self.tools.k8s_connection,
            "gatekeeper-audit",
            "audit-interval=1",
        )
        await wait_for_application_status(
            self.k8s_model, "gatekeeper-audit", status="active"
        )

        log("Running list-violations action")
        total_violations = 0
        while total_violations == 0:
            action = await unit.run_action("list-violations")
            await action.wait()
            assert action.status == "completed"
            assert "constraint-violations" in action.results
            constraint_violations = json.loads(action.results["constraint-violations"])
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

        log("Deploying the gatekeeper charm")
        webhook = await self.k8s_model.deploy(
            "gatekeeper-controller-manager",
            channel=self.tools.charm_channel,
            trust=True,
        )
        while (
            status := webhook.units[0].workload_status if webhook.units else None
        ) != "active":
            assert status not in ("blocked", "error")
            await asyncio.sleep(5)
        log("Deleting the gatekeeper charm")
        await webhook.destroy()

        interval = await self.tools.run(
            "juju", "model-config", "update-status-hook-interval"
        )
        interval = interval[0].strip()
        try:
            log("Decrease update status hook interval")
            await self.tools.run(
                "juju", "model-config", "update-status-hook-interval=5s"
            )
            log("Waiting for status to change to blocked")
            while (
                status := audit.units[0].workload_status if audit.units else None
            ) != "blocked":
                assert status != "error"
                await asyncio.sleep(5)
            log("Reconcile resources")
            await unit.run_action("reconcile-resources")
            while (
                status := audit.units[0].workload_status if audit.units else None
            ) != "active":
                assert status != "error"
                await asyncio.sleep(5)
        finally:
            await self.tools.run(
                "juju", "model-config", f"update-status-hook-interval={interval}"
            )
