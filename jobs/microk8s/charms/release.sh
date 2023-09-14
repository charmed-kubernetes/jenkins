#!/usr/bin/env bash
set -eux

## Requirements
## - Juju (>= 3.1)

## Secrets
## - CHARMCRAFT_AUTH: charmcraft credentials. output of `charmcraft login --export auth; cat auth`

# JUJU_CLOUD="aws/us-east-1"
JUJU_CLOUD="vsphere/Boston"
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
  --model-default datastore=vsanDatastore \
  --model-default primary-network=VLAN_2763 \
  --model-default force-vm-hardware-version=17 \
  --config caas-image-repo=rocks.canonical.com/cdk/jujusolutions \
  --bootstrap-image=juju-ci-root/templates/jammy-test-template \
  --bootstrap-base ubuntu@22.04 \
  --bootstrap-constraints "mem=8G cores=2 arch=amd64"

cd jobs/microk8s/charms

# TODO(neoaggelos): attempt with proxy
export MK8S_PROXY=http://squid.internal:3128
export MK8S_NO_PROXY=127.0.0.1,10.0.0.0/8,192.168.0.0/16,172.16.0.0/12,localhost

timeout 6h python release.py
