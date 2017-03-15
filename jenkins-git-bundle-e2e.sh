#!/usr/bin/env bash
# Runs the full suite of e2e-runner and gubernator scripts on jenkins.

set -o errexit  # Exit when an individual command fails.
set -o nounset  # Exit when undeclaried variables are used.
set -o pipefail  # The exit status of the last command is returned.
set -o xtrace  # Print the commands that are executed.

CLOUD=${1:-"gce"}
GIT_URL=${2:-"https://github.com/juju-solutions/bundle-kubernetes-core.git"}
GIT_BRANCH=${3:-"master"}
# The directory to use for this script, should be WORKSPACE, but can be PWD.
SCRIPT_DIRECTORY=${WORKSPACE:-${PWD}}
# The path to the archive of the JUJU_DATA directory for the specific cloud.
JUJU_DATA_TAR="/var/lib/jenkins/juju/juju_${CLOUD}.tar.gz"
# Uncompress the file that contains the Juju data to the workspace directory.
tar -xvzf ${JUJU_DATA_TAR} -C ${SCRIPT_DIRECTORY}

# Define a unique model name for this run.
MODEL=${BUILD_TAG:-"no-model-defined"}
# Set the output directory to store the results.
OUTPUT_DIRECTORY=${SCRIPT_DIRECTORY}/artifacts

# Set the JUJU_DATA directory for this jenkins workspace.
export JUJU_DATA=${SCRIPT_DIRECTORY}/juju
export JUJU_REPOSITORY=${SCRIPT_DIRECTORY}/charms
source ${SCRIPT_DIRECTORY}/define-juju.sh
# Catch all EXITs from this script and make sure to destroy the model.
trap "juju destroy-model -y ${MODEL} || true" EXIT

# Deploy the bundle and add the kubernetes-e2e charm.
${SCRIPT_DIRECTORY}/juju-deploy-git-bundle.sh ${MODEL} ${GIT_URL} ${GIT_BRANCH}

# Let the deployment complete.
${SCRIPT_DIRECTORY}/wait-cluster-ready.sh

# Run the end to end tests and 
${SCRIPT_DIRECTORY}/run-e2e-tests.sh ${OUTPUT_DIRECTORY}

# TODO Parse output and exit one on failure, or zero on success.
