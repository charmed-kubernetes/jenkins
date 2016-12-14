#!/usr/bin/env bash
# Runs the full suite of e2e-runner and gubernator scripts on your local host.

set -o errexit  # Exit when an individual command fails.
set -o nounset  # Exit when undeclaried variables are used.
set -o pipefail  # The exit status of the last command is returned.
set -o xtrace  # Print the commands that are executed.

source ./export-local-env.sh
# Ensure the workspace directory exists.
if [[ ! -d ${WORKSPACE} ]]; then
  mkdir -p ${WORKSPACE}
fi 

# The path to the archive of the JUJU_DATA directory for the specific cloud.
JUJU_DATA_TAR="${HOME}/.ssh/juju_${CLOUD}.tar.gz"
# Uncompress the file that contains the Juju data to the workspace directory.
tar -xvzf ${JUJU_DATA_TAR} -C ${WORKSPACE}

# Set the JUJU_DATA directory for this jenkins workspace.
export JUJU_DATA=${WORKSPACE}/juju
# Set the model to a unique name for this run.
export MODEL=${BUILD_TAG}
# Set the output directory to store the results.
export OUTPUT_DIRECTORY=${WORKSPACE}/artifacts

# Deploy a Kubernetes cluster and the e2e charm, and run the test action.
./e2e-runner.sh ${MODEL} ${OUTPUT_DIRECTORY}

# Formats the data and upload to GCE.
./gubernator.sh ${OUTPUT_DIRECTORY}
