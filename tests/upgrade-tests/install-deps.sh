#!/usr/bin/env bash
set -eux

# Installs dependencies needed for upgrade tests
# Can be run again to upgrade dependencies.

sudo pip3 install -U pytest pytest-asyncio asyncio_extras juju
