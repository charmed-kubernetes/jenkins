#!/bin/bash -eux

## Requirements
## - LXD (initialized)

## Configuration
## - REPOSITORY: Repository to pull the MicroK8s charm code from
## - BRANCH: Tag to checkout
## - RELEASE_TO_EDGE: Release uploaded revision to CharmHub edge
## - JOB_NAME: from jenkins
## - BUILD_NUMBER: from jenkins

## Secrets
## - CHARMCRAFT_AUTH: charmcraft credentials. output of `charmcraft login --charm microk8s --export auth; cat auth`

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
  sudo lxc delete $container --force
  set -e
}
trap cleanup EXIT

# Launch local LXD container to publish to charmcraft
# TODO: charmcraft 1.4.0 is needed for CHARMCRAFT_AUTH support. Drop --candidate once 1.4.0 is out on stable.
sudo lxc launch ubuntu:20.04 $container
timeout 5m bash -c "
  until sudo lxc shell $container -- bash -c 'snap install charmcraft --classic --candidate'; do
    sleep 3
  done
"

# Build charm and fetch
sudo lxc shell $container -- bash -c "git clone ${REPOSITORY} -b ${BRANCH} charm"
sudo lxc shell $container -- bash -c "apt-get update && apt-get install build-essential -y"
sudo lxc shell $container --env CHARMCRAFT_MANAGED_MODE=1 -- bash -c "cd charm && charmcraft build -v"

# Upload to CharmHub, and optionally release
upload_args=''
if [[ $RELEASE_TO_EDGE == 'true' ]]; then
  upload_args="$upload_args --release edge"
fi
sudo lxc shell $container --env CHARMCRAFT_AUTH="$CHARMCRAFT_AUTH" -- bash -c "cd charm && charmcraft upload *.charm $upload_args"
