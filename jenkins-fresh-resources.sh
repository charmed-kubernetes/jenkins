#!/usr/bin/env bash
# Deploys the test bundle, attaches resources, and runs bundletester.

set -o errexit  # Exit when an individual command fails.
set -o pipefail  # The exit status of the last command is returned.
set -o xtrace  # Print the commands that are executed.

# The cloud is an option for this script, default to gce.
CLOUD=${CLOUD:-"gce"}
# The directory to use for this script, should be WORKSPACE, but can be PWD.
SCRIPT_DIRECTORY=${WORKSPACE:-${PWD}}

# The path to the archive of the JUJU_DATA directory for the specific cloud.
JUJU_DATA_TAR="/var/lib/jenkins/juju/juju_${CLOUD}.tar.gz"
# Uncompress the file that contains the Juju data to the workspace directory.
tar -xvzf ${JUJU_DATA_TAR} -C ${SCRIPT_DIRECTORY}

# Set the JUJU_DATA directory for this jenkins workspace.
export JUJU_DATA=${SCRIPT_DIRECTORY}/juju
export JUJU_REPOSITORY=${SCRIPT_DIRECTORY}/charms

# Define a unique model name for this run.
MODEL=${1:-${BUILD_TAG}}
# Set the bundle to deploy.
BUNDLE=${2:-"kubernetes-core"}
# Set the directory to find the resources in.
RESOURCES_DIRECTORY=${3:-"resources"}
# Set the directory to save the output.
OUTPUT_DIRECTORY=${4:"artifacts/bundletester"}

# Deploy the bundle and add the kubernetes-e2e charm.
${SCRIPT_DIRECTORY}/juju-deploy-test-bundle.sh ${MODEL} ${BUNDLE}

# Run a fresh deploy with resources copied from another jenkins job.
${SCRIPT_DIRECTORY}/juju-attach-resources.sh ${RESOURCES_DIRECTORY}

# Let the deployment complete.
${SCRIPT_DIRECTORY}/wait-cluster-ready.sh

# Run bundletester against the model.
${SCRIPT_DIRECTORY}/run-bundletester.sh ${BUNDLE} ${OUTPUT_DIRECTORY}

# According to the design bundletester results verify new resources.
# The e2e tests can be run in a non blocking downstream job.

# TODO Remember to destroy the model when done.
