#!/usr/bin/env bash
# Deploys the test bundle, attaches resources, and runs bundletester.

set -o errexit  # Exit when an individual command fails.
set -o pipefail  # The exit status of the last command is returned.
set -o xtrace  # Print the commands that are executed.

# Define a unique model name for this run.
MODEL=${1:-${BUILD_TAG}}
# Set the bundle to deploy.
BUNDLE=${2:-"kubernetes-core"}
# Set the directory to find the resources in.
RESOURCES_DIRECTORY=${3:-"resources"}
# Set the directory to save the output.
OUTPUT_DIRECTORY=${4:"artifacts/bundletester"}

# Deploy the bundle and add the kubernetes-e2e charm.
./juju-deploy-test-bundle.sh ${MODEL} ${BUNDLE}

# Run a fresh deploy with resources copied from another jenkins job.
./juju-attach-resources.sh ${RESOURCES_DIRECTORY}

# Let the deployment complete.
./wait-cluster-ready.sh

# Run bundletester against the model.
./run-bundletester.sh ${BUNDLE} ${OUTPUT_DIRECTORY}

# According to the design bundletester results verify new resources.
# The e2e tests can be run in a non blocking downstream job.

# TODO Remember to destroy the model when done.
