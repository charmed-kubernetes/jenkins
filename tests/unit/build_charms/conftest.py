"""Ensure that path is included in PYTHONPATH before tests are run."""

import importlib
import sys
import pytest


@pytest.fixture(scope="package")
def builder_local():
    sys.path.append("jobs/build-charms")
    builder_local = importlib.import_module("builder_local")

    yield builder_local

    sys.path.remove("jobs/build-charms")
    del sys.modules["builder_local"]
    del builder_local


@pytest.fixture(scope="package")
def main():
    sys.path.append("jobs/build-charms")
    main = importlib.import_module("main")

    yield main

    sys.path.remove("jobs/build-charms")
    del sys.modules["main"]
    del main
