#!/usr/bin/env bash
# Deploys a kubernetes bundle, and the kubernetes-e2e charm adding relations.

set -o errexit  # Exit when an individual command fails.
set -o pipefail  # The exit status of the last command is returned.
set -o xtrace  # Print the commands that are executed.

echo "${0} started at `date`."

# First argument is the controller name for this build.
CONTROLLER=${1:-"controller-is-undefined"}
# Second argument is the model name for this build.
MODEL=${2:-"model-is-undefined"}
# Third argument is the bundle name.
BUNDLE=${3:-"canonical-kubernetes"}

# Create a model just for this run of the tests.
juju add-model -c ${CONTROLLER} ${MODEL}
# Set test mode on the deployment so we dont bloat charm-store deployment count
juju model-config -m ${CONTROLLER}:${MODEL} test-mode=true

# Deploy the kubernetes bundle.
juju deploy -m ${CONTROLLER}:${MODEL} ${BUNDLE}
# TODO Check for a second worker, the bundle could already define one.
# TODO Check for the e2e charm, the bundle could already define one.
# Deploy the e2e charm and make the relations.
juju deploy -m ${CONTROLLER}:${MODEL} cs:~containers/kubernetes-e2e
juju relate -m ${CONTROLLER}:${MODEL} kubernetes-e2e easyrsa
juju relate -m ${CONTROLLER}:${MODEL} \
  kubernetes-e2e:kube-control kubernetes-master:kube-control
juju relate -m ${CONTROLLER}:${MODEL} \
  kubernetes-e2e:kubernetes-master kubernetes-master:kube-api-endpoint

juju config -m ${CONTROLLER}:${MODEL} kubernetes-worker allow-privileged=true
juju config -m ${CONTROLLER}:${MODEL} kubernetes-master allow-privileged=true

# NOTE This script only deploys the bundle and charms, no waiting is done here!

echo "${0} completed successfully at `date`."
