#!/usr/bin/env bash
# Push the kubernetes charm code, release the charms and grant everyone access.

set -o errexit  # Exit when an individual command fails.
set -o pipefail  # The exit status of the last command is returned.
set -o xtrace  # Print the commands that are executed.

SCRIPT_DIR="$( cd "$( dirname "${0}" )" && pwd )"
if [[ -z "${WORKSPACE}" ]]; then
  export WORKSPACE=${PWD}
fi

ID=${1:-"containers"}
CHANNEL=${2}

CHANNEL_FLAG=""
if [[ -n "${CHANNEL}" ]]; then
  CHANNEL_FLAG="--channel=${CHANNEL}"
fi

# The cloud is an option for this script, default to gce.
CLOUD=${CLOUD:-"gce"}
# The path to the archive of the JUJU_DATA directory for the specific cloud.
JUJU_DATA_TAR="/var/lib/jenkins/juju/juju_${CLOUD}.tar.gz"
# Uncompress the file that contains the Juju data to the workspace directory.
tar -xvzf ${JUJU_DATA_TAR} -C ${WORKSPACE}

# Set the JUJU_DATA directory for this jenkins workspace.
export JUJU_DATA=${SCRIPT_DIR}/juju
export JUJU_REPOSITORY=${SCRIPT_DIR}/charms

# Define the juju functions.
source ${SCRIPT_DIR}/define-juju.sh

BUNDLE_REPOSITORY="https://github.com/juju-solutions/bundle-canonical-kubernetes.git"
git clone ${BUNDLE_REPOSITORY} bundle

bundle/bundle -o ./bundles/cdk-flannel -c ${CHANNEL} k8s/cdk cni/flannel
bundle/bundle -o ./bundles/core-flannel -c ${CHANNEL} k8s/core cni/flannel

# Some of the files in JUJU_DATA my not be owned by the ubuntu user, fix that.
CHOWN_CMD="sudo chown -R ubuntu:ubuntu /home/ubuntu/.local/share/juju"
# Create a model just for this run of the tests.
in-charmbox "${CHOWN_CMD} && charm login"

CDK="cs:~${ID}/bundle/canonical-kubernetes"
CORE="cs:~${ID}/bundle/kubernetes-core"

# The bundles are in /home/ubuntu/workspace inside the container.
CONTAINER_PATH=/home/ubuntu/workspace/bundles

# Build the charm push command from the variables.
PUSH_CMD="charm push ${CONTAINER_PATH}/cdk-flannel ${CDK}"
# Run the push command and capture the id of the bundle.
CDK_REVISION=`${PUSH_CMD} | head -1 | awk '{print $2}'`
charm release ${CHANNEL_FLAG} ${CDK_REVISION}

PUSH_CMD="charm push ${CONTAINER_PATH}/core-flannel ${CORE}"
# Run the push command and capture the id of the bundle.
CORE_REVISION=`${PUSH_CMD} | head 1 | awk '{print $2}'`
charm release ${CHANNEL_FLAG} ${CORE_REVISION}

echo "${0} completed successfully at `date`."
