#!/usr/bin/env bash
# Runs the full suite of e2e tests and gubernator scripts on jenkins.

set -o errexit  # Exit when an individual command fails.
set -o nounset  # Exit when undeclaried variables are used.
set -o pipefail  # The exit status of the last command is returned.
set -o xtrace  # Print the commands that are executed.

# The path to the archive of the JUJU_DATA directory for the specific cloud.
JUJU_DATA_TAR="/var/lib/jenkins/juju/juju_${CLOUD}.tar.gz"
# Uncompress the file that contains the Juju data to the workspace directory.
tar -xvzf ${JUJU_DATA_TAR} -C ${WORKSPACE}

# Set the Juju envrionment variables for this jenkins job.
export JUJU_DATA=${WORKSPACE}/juju
export JUJU_REPOSITORY=${WORKSPACE}/charms

# Define a unique model name for this run.
MODEL=${BUILD_TAG}
# Set the output directory to store the results.
OUTPUT_DIRECTORY=${WORKSPACE}/artifacts
# Set the bundle name to use.
BUNDLE=kubernetes-core

source ./define-juju.sh
# Grab the user id and group id of this current user.
GROUP_ID=$(id -g)
USER_ID=$(id -u)
# Change the permissions back to the current user so jenkins can clean up.
CHOWN_CMD="sudo chown -R ${USER_ID}:${GROUP_ID} /home/ubuntu/.local/share/juju"
# Catch all EXITs from this script and make sure to destroy the model.
trap "juju destroy-model -y ${MODEL} || in-jujubox ${CHOWN_CMD} || true" EXIT

# Deploy the bundle and add the kubernetes-e2e charm.
./juju-deploy-test-bundle.sh ${MODEL} ${BUNDLE}

# Let the deployment complete.
./wait-cluster-ready.sh

# Run the end to end tests and copy results to the output directory.
./run-e2e-tests.sh ${OUTPUT_DIRECTORY}

# Formats the output data and upload to GCE.
./gubernator.sh ${OUTPUT_DIRECTORY}
