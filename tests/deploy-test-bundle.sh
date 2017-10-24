#!/usr/bin/env bash
# Deploys a kubernetes bundle, and the kubernetes-e2e charm adding relations.

set -o errexit  # Exit when an individual command fails.
set -o pipefail  # The exit status of the last command is returned.
set -o xtrace  # Print the commands that are executed.

echo "${0} started at `date`."

# First argument is the model namme for this build.
MODEL=${1:-"model-is-undefined"}
# The second argument is the bundle name.
BUNDLE=${2:-"canonical-kubernetes"}
# Create a model just for this run of the tests.
juju add-model ${MODEL}
# Set test mode on the deployment so we dont bloat charm-store deployment count
juju model-config -m ${MODEL} test-mode=1

# Deploy the kubernetes bundle.
juju deploy ${BUNDLE}
# TODO Check for a second worker, the bundle could already define one.
# TODO Check for the e2e charm, the bundle could already define one.
# Deploy the e2e charm and make the relations.
juju deploy cs:~containers/kubernetes-e2e
juju relate kubernetes-e2e easyrsa
juju add-relation kubernetes-e2e:kube-control kubernetes-master:kube-control
juju add-relation kubernetes-e2e:kubernetes-master kubernetes-master:kube-api-endpoint

juju config kubernetes-worker allow-privileged=true
juju config kubernetes-master allow-privileged=true

# NOTE This script only deploys the bundle and charms, no waiting is done here!

echo "${0} completed successfully at `date`."
