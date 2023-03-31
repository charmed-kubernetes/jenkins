#!/bin/bash -eux

## Requirements
## - Juju (>= 2.9)
## - LXD (initialized)

## Configuration
## - REPOSITORY: Repository to pull the MicroK8s charm code from
## - TAG: Tag to checkout
## - CHARM_NAME: Name of MicroK8s charm (default: microk8s)
## - FROM_CHANNEL: Run integration tests against this channel. (default: edge)
## - TO_CHANNEL: After tests pass, charm will be pushed to this channel. (default: stable)
## - CLUSTER_SIZE: Cluster size for the integration tests.
## - SNAP_CHANNELS: MicroK8s snap channels to test (space separated list).
## - SERIES: Run tests for these OS series (space separated list) (default: focal jammy).
## - SKIP_TESTS: Skip tests for promoting release (NOT RECOMMENDED).
## - SKIP_RELEASE: Skip promoting build to TO_CHANNEL after tests succeed.
## - JOB_NAME: from jenkins
## - BUILD_NUMBER: from jenkins

## Secrets
## - CHARMCRAFT_AUTH: charmcraft credentials. output of `charmcraft login --export auth; cat auth`
## - JUJUCONTROLLERS: controllers.yaml configuration file for Juju
## - JUJUACCOUNTS: accounts.yaml configuration file for Juju

_DIR="${BASH_SOURCE%/*}"
if [[ ! -d "$_DIR" ]]; then _DIR="$PWD"; fi
. "$_DIR/../../build-charms/charmcraft-lib.sh"

## default optional variables
JOB_NAME="${JOB_NAME:-unnamed-job}"
BUILD_NUMBER="${BUILD_NUMBER:-0}"
export JUJU_MODEL=${JOB_NAME}-${BUILD_NUMBER}

# Cleanup old containers
ci_lxc_delete "${JOB_NAME}"

# Configure cleanup routine
export charmcraft_lxc="${JOB_NAME}-${BUILD_NUMBER}"
function cleanup() {
  ci_lxc_delete $charmcraft_lxc
  set +e
  juju destroy-model $JUJU_MODEL -y --timeout 1m --force
  rm -rf $JUJU_DATA
  set -e
}
trap cleanup EXIT

# Launch container
ci_charmcraft_launch $charmcraft_lxc

# Retrieve revision from CharmHub API. For reference (http://api.snapcraft.io/docs/charms.html#charm_info). Note that `head -1` is needed because the info endpoint returns an entry for each base.
#
# curl 'https://api.charmhub.io/v2/charms/info/microk8s?fields=channel-map' | jq -r '.["channel-map"][] | select(.channel.name == "edge") | select(.channel.base.architecture == "amd64") | .revision.revision' | head -1
# 20
revision=$(curl --silent 'https://api.charmhub.io/v2/charms/info/microk8s?fields=channel-map' | jq -r '.["channel-map"][] | select(.channel.name == "'"$FROM_CHANNEL"'") | select(.channel.base.architecture == "amd64") | .revision.revision' | head -1)

# Run tests
if [[ "$SKIP_TESTS" != 'true' ]]; then
  export JUJU_DATA=$PWD/data
  mkdir -p $JUJU_DATA
  cp $JUJUACCOUNTS $JUJU_DATA/accounts.yaml
  cp $JUJUCONTROLLERS $JUJU_DATA/controllers.yaml

  export PROXY=http://squid.internal:3128
  export NO_PROXY=10.0.0.0/8,192.168.0.0/16,127.0.0.1

  juju add-model $JUJU_MODEL
  juju model-config http-proxy=$PROXY https-proxy=$PROXY ftp-proxy=$PROXY no-proxy=$NO_PROXY

  git clone $REPOSITORY -b $TAG microk8s-charm
  cd microk8s-charm

  python3 -m venv venv
  . venv/bin/activate
  pip install 'tox<4'

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
  export MK8S_SERIES=$SERIES

  tox -e integration -- --model $JUJU_MODEL -n 3
fi

# Release
if [[ "$SKIP_RELEASE" != 'true' ]]; then
  ci_charmcraft_promote $charmcraft_lxc $CHARM_NAME $revision $TO_CHANNEL
fi
