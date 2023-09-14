#!/usr/bin/env bash 
set -eux

## Requirements
## - Juju (>= 3.1)

## Secrets
## - CHARMCRAFT_AUTH: charmcraft credentials. output of `charmcraft login --export auth; cat auth`

JUJU_CLOUD="aws/us-east-1"
CONTROLLER="${CONTROLLER:-'release-microk8s-charm'}"
DRY_RUN="${DRY_RUN:-'true'}"
SKIP_TESTS="${SKIP_TESTS:-'false'}"
export REPOSITORY="${TESTS_REPOSITORY:-''}"
export BRANCH="${TESTS_BRANCH:-''}"
TO_CHANNEL="${TO_CHANNEL:-'latest/edge/testing'}"
FROM_CHANNEL="${FROM_CHANNEL:-'latest/edge'}"


function juju::cleanup() {
  controller=$1
  if ! timeout 4m juju destroy-controller -y --destroy-all-models --destroy-storage "${controller}"; then
    timeout 4m juju kill-controller -y "${controller}" || true
  fi
}
trap "juju::cleanup ${CONTROLLER}" EXIT

juju::cleanup "${CONTROLLER}"

pip install -r jobs/microk8s/charms/requirements.txt

juju bootstrap "${JUJU_CLOUD}" "${CONTROLLER}" \
  --model-default test-mode=true \
  --model-default resource-tags="owner=k8sci" \
  --bootstrap-constraints "mem=8G cores=2"

cd jobs/microk8s/charms
timeout 6h python release.py
