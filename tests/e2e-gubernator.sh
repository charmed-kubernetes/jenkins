#!/usr/bin/env bash
# Runs the full suite of e2e tests and gubernator scripts on jenkins.

set -o errexit  # Exit when an individual command fails.
set -o nounset  # Exit when undeclaried variables are used.
set -o pipefail  # The exit status of the last command is returned.
set -o xtrace  # Print the commands that are executed.

source "utils/retry.sh"

# The cloud is an option for this script, default to gce.
CLOUD=${CLOUD:-"gce"}
CONTROLLER=${CONTROLLER:-"jenkins-ci-google"}
# The directory to use for this script, should be WORKSPACE, but can be PWD.
SCRIPT_DIRECTORY=${WORKSPACE:-${PWD}}

# Define a unique model name for this run.
MODEL=${BUILD_TAG:-"default-model"}
# Set the output directory to store the results.
OUTPUT_DIRECTORY=${SCRIPT_DIRECTORY}/artifacts
# Set the bundle name to use.
BUNDLE=canonical-kubernetes

# Set the Juju envrionment variables for this script.
export JUJU_REPOSITORY=${SCRIPT_DIRECTORY}/build/charms

mkdir -p ${JUJU_REPOSITORY}
# Catch all EXITs from this script and make sure to destroy the model.
trap "sleep 10 && juju destroy-model -y ${CONTROLLER}:${MODEL}" EXIT

# Deploy the bundle and add the kubernetes-e2e charm.
${SCRIPT_DIRECTORY}/tests/deploy-test-bundle.sh ${CONTROLLER} ${MODEL} ${BUNDLE}

# Let the deployment complete.
${SCRIPT_DIRECTORY}/tests/wait-cluster-ready.sh ${CONTROLLER} ${MODEL}

# Run the end to end tests and copy results to the output directory.
# Retry 3 times. The second and third retries should be quick since
# we have any images cached
retry ${SCRIPT_DIRECTORY}/tests/run-e2e-tests.sh ${CONTROLLER} ${MODEL} ${OUTPUT_DIRECTORY}

# Formats the output data and upload to GCE.
${SCRIPT_DIRECTORY}/tests/upload-e2e-results-to-gubernator.sh ${OUTPUT_DIRECTORY}
