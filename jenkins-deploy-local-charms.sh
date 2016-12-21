#!/usr/bin/env bash
# Deploy the local charms (built in a prevous step) and since they are local
# charms we do have to attach local resources (also built in previous step).

set -o errexit  # Exit when an individual command fails.
set -o pipefail  # The exit status of the last command is returned.
set -o xtrace  # Print the commands that are executed.

CLOUD=${CLOUD:-"gce"}

# The path to the archive of the JUJU_DATA directory for the specific cloud.
JUJU_DATA_TAR="/var/lib/jenkins/juju/juju_${CLOUD}.tar.gz"
# Uncompress the file that contains the Juju data to the workspace directory.
tar -xvzf ${JUJU_DATA_TAR} -C ${WORKSPACE}

# Set the JUJU_DATA directory for this jenkins workspace.
export JUJU_DATA=${WORKSPACE}/juju
export JUJU_REPOSITORY=${WORKSPACE}/charms
# Define a unique model name for this run.
MODEL=${BUILD_TAG}

# Create a model, deploy, expose, relate all the Kubernetes charms.
./juju-deploy-local-charms.sh ${MODEL}

source ./define-juju.sh
# Catch all EXITs from this script and make sure to destroy the model.
trap "juju destroy-model -y ${MODEL} || true" EXIT

# Attach the resources built from a previous step.
./juju-attach-resources.sh ${}

juju status
