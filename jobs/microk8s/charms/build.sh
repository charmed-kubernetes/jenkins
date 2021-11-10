#!/bin/bash -eux

## Requirements
## - Juju (>= 2.9)
## - LXD (initialized)

## Configuration
## - REPOSITORY: Repository to pull the MicroK8s charm code from
## - TAG: Tag to checkout
## - RELEASE_TO_EDGE: Release uploaded revision to CharmHub edge
## - JOB_NAME: from jenkins
## - BUILD_NUMBER: from jenkins

## Secrets
## - JUJUCONTROLLERS: controllers.yaml configuration file for Juju
## - JUJUACCOUNTS: accounts.yaml configuration file for Juju

# Cleanup old containers
container_prefix="${JOB_NAME}"
old_containers=$(sudo lxc list -c n -f csv "${container_prefix}" | xargs)
if [[ ! -z $old_containers ]]; then
  echo Removing old containers, $old_containers
  sudo lxc delete --force $old_containers
fi

# Configure cleanup routine
container="${container_prefix}-${BUILD_NUMBER}"
function cleanup() {
  set +e
  sudo lxc shell $container -- bash -c 'charmcraft logout'
  sudo lxc delete $container --force
  juju destroy-model $JUJU_MODEL -y --timeout 1m --force
  rm -rf $JUJU_DATA
  set -e
}
trap cleanup EXIT

# Launch local LXD container to publish to charmcraft
sudo lxc launch ubuntu:20.04 $container
timeout 5m bash -c "
  until sudo lxc shell $container -- bash -c 'snap install charmcraft --classic'; do
    sleep 3
  done
"

# TODO: update when charmcraft supports non-interactive logins
# sudo lxc file push $CHARMCRAFT_CREDENTIALS $container/charmcraft.credentials
# sudo lxc shell $container -- bash -c 'mkdir -p ~/snap/charmcraft/common/config/charmcraft.credentials'
# sudo lxc shell $container -- bash -c 'cp charmcraft.credentials ~/snap/charmcraft/common/config/charmcraft.credentials'
sudo lxc shell $container -- bash -c 'charmcraft login'
sudo lxc shell $container -- bash -c 'charmcraft whoami'

# Spawn a new ubuntu instance on the Juju controller to run the build
export JUJU_DATA=$PWD/data
export JUJU_MODEL=${JOB_NAME}-${BUILD_NUMBER}
mkdir -p $JUJU_DATA
cp $JUJUACCOUNTS $JUJU_DATA/accounts.yaml
cp $JUJUCONTROLLERS $JUJU_DATA/controllers.yaml
export PROXY=http://squid.internal:3128
juju add-model $JUJU_MODEL
juju model-config http-proxy=$PROXY https-proxy=$PROXY ftp-proxy=$PROXY no-proxy=10.0.0.0/8,192.168.0.0/16,127.0.0.1
juju deploy ubuntu --constraints 'cores=8 mem=4G root-disk=20G allocate-public-ip=true'
juju-wait -e $JUJU_MODEL -w

# Install LXD and Charmcraft into builder machine
juju ssh ubuntu/leader -- 'sudo snap install lxd'
juju ssh ubuntu/leader -- 'sudo lxd init --auto'
juju ssh ubuntu/leader -- 'sudo usermod -a -G lxd ubuntu'
juju ssh ubuntu/leader -- 'sudo snap install charmcraft --classic'

# Build charm and fetch
juju ssh ubuntu/leader -- "git clone ${REPOSITORY} -b ${BRANCH} charm"
juju ssh ubuntu/leader -- 'cd charm && charmcraft build -v'
juju scp 'ubuntu/leader:charm/*.charm' ./microk8s.charm

# Push charm to LXD container and upload to CharmHub
sudo lxc file push ./microk8s.charm $container/microk8s.charm
sudo lxc shell $container -- bash -c 'charmcraft upload /microk8s.charm'

# Release to edge
charm=$(unzip -p ./microk8s.charm metadata.yaml | grep "name:" | cut -f2 -d:)
revision=$(sudo lxc shell $container -- bash -c "charmcraft revisions $charm 2>&1 | grep "^[0-9]" | head -1 | cut -f1 -d' '")
if [[ $RELEASE_TO_EDGE == 'true' ]]; then
  echo Release revision $revision of charm $charm to edge
  sudo lxc shell $container -- bash -c "charmcraft release $charm --revision $revision --channel edge"
fi
