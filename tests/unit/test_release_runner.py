import os
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
CI_BASH = ROOT / "ci.bash"
CONTAINER = ROOT / "jobs/release/container.sh"


def run_ci(tmp_path, result=None, deployment_status=None, cleanup_status=0):
    execute = "" if result is None else f'test::execute() {{ printf -v "$1" %s "{result}"; }}'
    deploy = ":" if deployment_status is None else f"exit {deployment_status}"
    script = f'''
source "{CI_BASH}"
compile::env() {{ :; }}
timestamp() {{ echo timestamp; }}
kv::set() {{ printf 'kv:%s\\n' "$1" >> calls; }}
juju::bootstrap::before() {{ :; }}
juju::bootstrap() {{ :; }}
juju::bootstrap::after() {{ :; }}
juju::model::speed-up() {{ :; }}
juju::deploy::before() {{ :; }}
juju::deploy::overlay() {{ :; }}
juju::deploy() {{ {deploy}; }}
juju::wait() {{ :; }}
juju::deploy::after() {{ :; }}
{execute}
test::report() {{ printf 'report:%s\\n' "$1" >> calls; }}
ci::cleanup() {{ printf 'cleanup\\n' >> calls; return {cleanup_status}; }}
ci::run
'''
    return subprocess.run(
        ["bash", "-c", script], cwd=tmp_path, text=True, capture_output=True
    )


@pytest.mark.parametrize(
    ("result", "expected"), [("True", 0), ("False", 1), ("Timeout", 124)]
)
def test_ci_run_maps_test_result_and_preserves_cleanup_status(tmp_path, result, expected):
    completed = run_ci(tmp_path, result=result, cleanup_status=9)

    assert completed.returncode == expected
    calls = (tmp_path / "calls").read_text()
    assert f"report:{result}" in calls
    assert "cleanup" in calls


def test_ci_run_propagates_deployment_exit_through_logging_pipeline(tmp_path):
    completed = run_ci(tmp_path, deployment_status=7, cleanup_status=9)

    assert completed.returncode == 7
    assert "cleanup" in (tmp_path / "calls").read_text()


def make_dispatch_workspace(tmp_path, activate=True):
    workspace = tmp_path / "workspace"
    spec_dir = workspace / "jobs/release"
    spec_dir.mkdir(parents=True)
    if activate:
        activate_path = workspace / ".tox/py/bin/activate"
        activate_path.parent.mkdir(parents=True)
        activate_path.write_text("")
    for scenario, name in {
        "bugfix": "bugfix-spec",
        "bugfix-upgrade": "bugfix-upgrade-spec",
        "release-upgrade": "release-upgrade-spec",
    }.items():
        (spec_dir / name).write_text('#!/bin/bash\nprintf "<%s>\\n" "$@"\n')
    return workspace


def run_dispatch(workspace, *args):
    env = os.environ | {"WORKSPACE": str(workspace), "TMPDIR": str(workspace / "tmp")}
    return subprocess.run(
        ["bash", str(CONTAINER), "validate", *args],
        text=True,
        capture_output=True,
        env=env,
    )


def test_container_dispatcher_preserves_quoted_scenario_arguments(tmp_path):
    workspace = make_dispatch_workspace(tmp_path)
    value = "1.34/stable; touch should-not-run"

    completed = run_dispatch(workspace, "bugfix", value, "jammy", "candidate")

    assert completed.returncode == 0
    assert f"<{value}>" in completed.stdout
    assert not (workspace / "should-not-run").exists()


def test_container_dispatcher_rejects_unknown_scenario(tmp_path):
    workspace = make_dispatch_workspace(tmp_path)

    completed = run_dispatch(workspace, "not-a-scenario")

    assert completed.returncode == 2


def test_container_dispatcher_requires_prepared_venv(tmp_path):
    workspace = make_dispatch_workspace(tmp_path, activate=False)

    completed = run_dispatch(workspace, "bugfix", "1.34/stable", "jammy", "candidate")

    assert completed.returncode != 0
    assert "missing prepared Python environment" in completed.stderr

def test_release_ssh_config_routes_connections_through_egress_proxy():
    completed = subprocess.run(
        ["ssh", "-G", "-F", str(ROOT / "jobs/release/ssh_config"), "10.246.153.40"],
        text=True,
        capture_output=True,
        check=True,
    )

    assert "proxycommand nc -X connect -x egress.ps7.internal:3128 %h %p" in completed.stdout
