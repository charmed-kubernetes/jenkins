#!/bin/bash -eux

## Requirements
## - Juju (>= 2.9)
## - LXD (initialized)

## Configuration
## - REPOSITORY: Repository to pull the MicroK8s charm code from
## - TAG: Tag to checkout
## - CHARM_NAME: Charm name to test (microk8s)
## - FROM_CHANNEL: Pull charm from this channel (latest/edge)
## - TO_CHANNEL: After running tests, release revision to this channel (latest/stable)
## - SKIP_TESTS: Do not run tests
## - SKIP_RELEASE: Do not release
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

# Retrieve revision from CharmHub API. For reference:
#
# curl --silent https://api.charmhub.io/v1/charm/microk8s-testing/releases -b ./snap/charmcraft/common/config/charmcraft.credentials  | jq '.["channel-map"][] | {channel: .channel, revision: .revision}'
# {
#   "channel": "latest/edge",
#   "revision": 9
# }
# {
#   "channel": "latest/stable",
#   "revision": 3
# }
revision=$(sudo lxc shell $container -- \
  bash -c "curl https://api.charmhub.io/v1/charm/$CHARM_NAME/releases -b ~/snap/charmcraft/common/config/charmcraft.credentials" \
    | jq -r ".[\"channel-map\"][] | select(.channel == \"$FROM_CHANNEL\") | .revision")

# Run tests
if [[ "$SKIP_TESTS" != 'true' ]]; then
  export JUJU_DATA=$PWD/data
  export JUJU_MODEL=${JOB_NAME}-${BUILD_NUMBER}
  mkdir -p $JUJU_DATA
  cp $JUJUACCOUNTS $JUJU_DATA/accounts.yaml
  cp $JUJUCONTROLLERS $JUJU_DATA/controllers.yaml

  export PROXY=http://squid.internal:3128
  export NO_PROXY=10.0.0.0/8,192.168.0.0/16,127.0.0.1

  juju add-model $JUJU_MODEL
  juju model-config http-proxy=$PROXY https-proxy=$PROXY ftp-proxy=$PROXY no-proxy=$NO_PROXY

  git clone $REPOSITORY -b $BRANCH microk8s-charm
  cd microk8s-charm

  python3 -m venv venv
  . venv/bin/activate
  pip install tox

  # workaround unneeded missing dependency charmcraft
  ln -s /usr/bin/false charmcraft
  export PATH=$PATH:$PWD

  export MK8S_CHARM=$CHARM_NAME
  export MK8S_CHARM_CHANNEL=$FROM_CHANNEL
  export MK8S_CLUSTER_SIZE=$CLUSTER_SIZE
  export MK8S_PROXY=$PROXY
  export MK8S_NO_PROXY=$NO_PROXY
  export MK8S_CONSTRAINTS='mem=2G cores=2 root-disk=20G'
  export MK8S_SNAP_CHANNELS=$SNAP_CHANNELS

  tox -e integration -- --model $JUJU_MODEL -n 3
fi

# Release
if [[ "$SKIP_RELEASE" != 'true' ]]; then
  sudo lxc shell $container -- bash -c "charmcraft release $CHARM_NAME --revision $revision --channel $TO_CHANNEL"
fi
