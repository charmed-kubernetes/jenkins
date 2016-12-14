#!/usr/bin/env bash
# Deploys a kubernetes bundle, and the kubernetes-e2e charm adding relations.

set -o errexit  # Exit when an individual command fails.
set -o pipefail  # The exit status of the last command is returned.
set -o xtrace  # Print the commands that are executed.

echo "${0} started at `date`."

# First argument is the model namme for this build.
MODEL=${1:-"model-is-undefined"}
# The second argument is the bundle name.
BUNDLE=${2:-"kubernetes-core"}
# Some of the files in JUJU_DATA my not be owned by the ubuntu user, fix that.
CHOWN_CMD="sudo chown -R ubuntu:ubuntu /home/ubuntu/.local/share/juju"
# Define the juju and in-jujubox functions.
source ./define-juju.sh
# Create a model just for this run of the tests.
in-jujubox "${CHOWN_CMD} && juju add-model ${MODEL}"

# Set test mode on the deployment so we dont bloat charm-store deployment count
juju model-config -m ${MODEL} test-mode=1

# Deploy the kubernetes bundle.
juju deploy ${BUNDLE}
# TODO Check for a second worker, the bundle could already define one.
# Add one more kubernetes node to the cluster.
juju add-unit kubernetes-worker
# TODO Check for the e2e charm, the bundle could already define one.
# Deploy the e2e charm and make the relations.
juju deploy cs:~containers/kubernetes-e2e
juju relate kubernetes-e2e kubernetes-master
juju relate kubernetes-e2e easyrsa

# NOTE This script only deploys the bundle and charms, no waiting is done here!

echo "${0} completed successfully at `date`."
