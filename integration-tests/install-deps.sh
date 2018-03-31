#!/usr/bin/env bash
set -eux

# Installs dependencies needed for upgrade tests
# Can be run again to upgrade dependencies.

sudo apt update -yq
sudo apt install -y unzip python3-pip python-pip squashfuse snapd
sudo snap install juju --classic
sudo snap install charm
sudo snap install conjure-up --classic
sudo pip2 install 'git+https://github.com/juju/juju-crashdump'
sudo pip2 install -U pyopenssl bundletester
sudo pip3 install -U pytest  pytest-asyncio asyncio_extras juju==0.7.2 requests pyyaml kubernetes
sudo pip3 install -U 'git+https://github.com/juju/amulet' # we need https://github.com/juju/amulet/pull/183

# Leaving those here in case we need to build a client from bleeding edge
# sudo pip2 install 'git+https://github.com/juju-solutions/bundletester' \
#                 'git+https://github.com/juju/juju-crashdump'
# sudo pip3 install 'git+https://github.com/juju/python-libjuju'
