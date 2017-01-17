#!/usr/bin/env bash
# Runs the full suite of e2e tests against deployed charms in jenkins.

set -o errexit  # Exit when an individual command fails.
set -o pipefail  # The exit status of the last command is returned.
set -o xtrace  # Print the commands that are executed.

if [ -z "${MODEL}" ]; then
  echo "Can not test, the model is undefined."
  exit 1 
fi

# The path to the archive of the JUJU_DATA directory for the specific cloud.
JUJU_DATA_TAR="/var/lib/jenkins/juju/juju_${CLOUD}.tar.gz"
# Uncompress the file that contains the Juju data to the workspace directory.
tar -xvzf ${JUJU_DATA_TAR} -C ${WORKSPACE}

# Set the Juju envrionment variables for this jenkins job.
export JUJU_DATA=${WORKSPACE}/juju
export JUJU_REPOSITORY=${WORKSPACE}/charms

# Set the output directory to store the results.
OUTPUT_DIRECTORY=${WORKSPACE}/artifacts

source ./define-juju.sh
# Catch all EXITs from this script and make sure to destroy the model.
trap "juju destroy-model -y ${MODEL} || true" EXIT

# Let the deployment complete.
./wait-cluster-ready.sh

# Run the end to end tests.
./run-e2e-tests.sh ${OUTPUT_DIRECTORY}
