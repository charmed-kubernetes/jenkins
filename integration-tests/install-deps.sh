#!/usr/bin/env bash
set -eux

# Installs dependencies needed for upgrade tests
# Can be run again to upgrade dependencies.

sudo add-apt-repository ppa:juju/stable -y
sudo add-apt-repository ppa:tvansteenburgh/ppa -y
sudo apt update -yq
sudo apt install -y unzip python3-pip python-pip squashfuse snapd charm-tools
sudo snap install juju --classic
sudo snap install conjure-up --classic
sudo pip2 install 'git+https://github.com/juju/juju-crashdump'
sudo pip2 install -U pyopenssl bundletester virtualenv
sudo pip3 install -U pytest  pytest-asyncio asyncio_extras juju requests pyyaml kubernetes
sudo pip3 install -U 'git+https://github.com/juju/amulet' # we need https://github.com/juju/amulet/pull/183

# Leaving those here in case we need to build a client from bleeding edge
# sudo pip2 install 'git+https://github.com/juju-solutions/bundletester' \
#                 'git+https://github.com/juju/juju-crashdump'
# sudo pip3 install 'git+https://github.com/juju/python-libjuju'
