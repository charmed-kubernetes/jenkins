#!/usr/bin/env bash
set -eux

# Installs dependencies needed for upgrade tests
# Can be run again to upgrade dependencies.

sudo apt update
sudo apt install -y python3-pip python-pip
sudo pip3 install -U pytest pytest-asyncio asyncio_extras juju requests pyyaml kubernetes
sudo pip2 install -U bundletester
sudo snap install conjure-up --classic
