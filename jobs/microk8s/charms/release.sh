#!/usr/bin/env bash 
set -eux

## Requirements
## - Juju (>= 3.1)

## Secrets
## - CHARMCRAFT_AUTH: charmcraft credentials. output of `charmcraft login --export auth; cat auth`

JUJU_CLOUD="aws/us-east-1"
CONTROLLER="release-microk8s-charm"


function juju::cleanup() {
  controller=$1
  if ! timeout 4m juju destroy-controller -y --destroy-all-models --destroy-storage "${controller}"; then
    timeout 4m juju kill-controller -y "${controller}" || true
  fi
}
trap "juju::cleanup ${CONTROLLER}" EXIT

juju::cleanup "${CONTROLLER}"
juju bootstrap "${JUJU_CLOUD}" "${CONTROLLER}" \
  --model-default test-mode=true \
  --model-default resource-tags="owner=k8sci" \
  --bootstrap-constraints "mem=8G cores=2"

pip install -r jobs/microk8s/requirements.txt
cd jobs/microk8s/charms
DRY_RUN=${DRY_RUN} SKIP_TESTS=${SKIP_TESTS}\
  BRANCH=${TESTS_BRANCH} REPOSITORY=${TESTS_REPOSITORY}\
  timeout 6h python release.py

exit 0
