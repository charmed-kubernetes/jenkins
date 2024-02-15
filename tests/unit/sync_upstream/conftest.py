"""Ensure that path is included in PYTHONPATH before tests are run."""

import importlib
import os
import sys
import pytest


@pytest.fixture(scope="package")
def cdkbot_creds():
    test_envs = {env: "test_val" for env in ("CDKBOT_GH_USR", "CDKBOT_GH_PSW")}
    restore = {env: os.environ.get(env) for env in test_envs}
    for env, env_var in test_envs.items():
        os.environ[env] = env_var

    yield os.environ

    for env, env_var in restore.items():
        if env_var is None:
            del os.environ[env]
        else:
            os.environ[env] = env_var


@pytest.fixture(scope="package")
def sync(cdkbot_creds):
    sys.path.append("jobs/sync-upstream")
    sync = importlib.import_module("sync")

    yield sync

    sys.path.remove("jobs/sync-upstream")
    del sys.modules["sync"]
    del sync
