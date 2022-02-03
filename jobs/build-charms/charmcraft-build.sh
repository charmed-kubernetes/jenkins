#!/bin/bash -eux

_DIR="${BASH_SOURCE%/*}"
if [[ ! -d "$_DIR" ]]; then _DIR="$PWD"; fi
. "$_DIR/charmcraft-lib.sh"

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
## - CHARMCRAFT_AUTH: charmcraft credentials. output of `charmcraft login --export auth; cat auth`

## default optional variables
JOB_NAME="${JOB_NAME:-unnamed-job}"
BUILD_NUMBER="${BUILD_NUMBER:-0}"
SUBDIR="${SUBDIR:-}"
RELEASE_TO_EDGE="${RELEASE_TO_EDGE:-}"
UPLOAD_CHARM="${UPLOAD_CHARM:-}"
COPY_CHARM="${COPY_CHARM:-}"

# Cleanup old containers
ci_lxc_delete "${JOB_NAME}"

# Configure cleanup routine
container="${JOB_NAME}-${BUILD_NUMBER}"
trap 'ci_lxc_delete $container' EXIT

ci_charmcraft_launch $container
ci_charmcraft_pack $container ${REPOSITORY} ${BRANCH} "${SUBDIR}"
if [[ "$UPLOAD_CHARM" == 'true' ]]; then
  ci_charmcraft_release $container $RELEASE_TO_EDGE
fi

if [[ -n "$COPY_CHARM" ]]; then
  ci_charmcraft_copy $container $COPY_CHARM
fi
