#!/bin/bash -eux

_DIR="${BASH_SOURCE%/*}"
if [[ ! -d "$_DIR" ]]; then _DIR="$PWD"; fi
. "$_DIR/../../cilib.sh"

## Requirements
## - LXD (initialized)

## Configuration
## - REPOSITORY: Repository to pull the charm code from
## - BRANCH: Tag to checkout
## - SUBDIR: Subdirectory under repository where charm exists
## - RELEASE_TO_EDGE: Release uploaded revision to CharmHub edge
## - UPLOAD_CHARM: Upload charm to charmhub.io
## - COPY_CHARM: Copy charm to local path
## - JOB_NAME: from jenkins
## - BUILD_NUMBER: from jenkins


## Secrets
## - CHARMCRAFT_AUTH: charmcraft credentials. output of `charmcraft login --charm microk8s --export auth; cat auth`

## default optional variables
COPY_CHARM="${COPY_CHARM:=}"
JOB_NAME="${JOB_NAME:=unnamed-job}"
BUILD_NUMBER="${BUILD_NUMBER:=0}"
RELEASE_TO_EDGE="${RELEASE_TO_EDGE:=false}"
UPLOAD_CHARM="${UPLOAD_CHARM:=false}"

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
#trap cleanup EXIT

# Launch local LXD container to publish to charmcraft
ci_lxc_launch ubuntu:20.04 $container
until sudo lxc shell $container -- bash -c 'snap install charmcraft --classic'; do
  sleep 3
  echo 'retrying charmcraft install'
done


# Build charm and fetch
sudo lxc shell $container -- bash -c "git clone ${REPOSITORY} -b ${BRANCH} charm"
sudo lxc shell $container --env CHARMCRAFT_MANAGED_MODE=1 -- bash -c "cd charm/$SUBDIR && charmcraft build -v"

if [[ "$UPLOAD_CHARM" == 'true' ]]; then
  # Upload to CharmHub, and optionally release
  upload_args=''
  if [[ $RELEASE_TO_EDGE == 'true' ]]; then
    upload_args="$upload_args --release edge"
  fi
  sudo lxc shell $container --env CHARMCRAFT_AUTH="$CHARMCRAFT_AUTH" -- bash -c "cd charm/$SUBDIR && charmcraft upload *.charm $upload_args"
fi

if [[ -n "$COPY_CHARM" ]]; then
  # Copy charm out of the container to a local directory
  for charm in $(sudo lxc exec $container -- bash -c "ls /root/charm/$SUBDIR/*.charm"); do
    sudo lxc file pull ${container}${charm} $COPY_CHARM
  done
fi
