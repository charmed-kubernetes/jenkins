"""Ensure that path is included in PYTHONPATH before tests are run."""
import importlib
import sys
import pytest


@pytest.fixture(scope="package")
def charms():
    sys.path.append("jobs/build-charms")
    charms = importlib.import_module("charms")

    yield charms

    sys.path.remove("jobs/build-charms")
    del sys.modules["charms"]
    del charms
