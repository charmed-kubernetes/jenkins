#!/usr/bin/env bash
# Deploy the local charms (built in a prevous step) and since they are local
# charms we do have to attach local resources (also built in previous step).

set -o errexit  # Exit when an individual command fails.
set -o pipefail  # The exit status of the last command is returned.
set -o xtrace  # Print the commands that are executed.

# The cloud is an option for this script, default to gce.
CLOUD=${CLOUD:-"gce"}
# The directory to use for this script, should be WORKSPACE, but can be PWD.
SCRIPT_DIRECTORY=${WORKSPACE:-${PWD}}

# The path to the archive of the JUJU_DATA files for the specific cloud.
JUJU_DATA_TAR="/var/lib/jenkins/juju/juju_${CLOUD}.tar.gz"
# Uncompress the file that contains the Juju data to the workspace directory.
tar -xvzf ${JUJU_DATA_TAR} -C ${SCRIPT_DIRECTORY}

CHARMS_BUILDS=${SCRIPT_DIRECTORY}/charms/builds
# Expand all the charm archives to the charms/builds directory.
tar -xzf ${CHARMS_BUILDS}/easyrsa.tar.gz -C ${CHARMS_BUILDS}
tar -xzf ${CHARMS_BUILDS}/etcd.tar.gz -C ${CHARMS_BUILDS}
tar -xzf ${CHARMS_BUILDS}/flannel.tar.gz -C ${CHARMS_BUILDS}
tar -xzf ${CHARMS_BUILDS}/kubeapi-load-balancer.tar.gz -C ${CHARMS_BUILDS}
tar -xzf ${CHARMS_BUILDS}/kubernetes-e2e.tar.gz -C ${CHARMS_BUILDS}
tar -xzf ${CHARMS_BUILDS}/kubernetes-master.tar.gz -C ${CHARMS_BUILDS}
tar -xzf ${CHARMS_BUILDS}/kubernetes-worker.tar.gz -C ${CHARMS_BUILDS}

# Define a unique model name for this run.
export MODEL=${MODEL:-${BUILD_TAG}}

# Create a model, deploy, expose, relate all the Kubernetes charms.
${SCRIPT_DIRECTORY}/juju-deploy-local-charms.sh ${MODEL}

# Attach the resources built from a previous step.
${SCRIPT_DIRECTORY}/juju-attach-resources.sh resources

echo "Charms deployed and resources attached to ${MODEL} at `date`."

# Set the Juju environment variables for this script.
export JUJU_DATA=${SCRIPT_DIRECTORY}/juju
export JUJU_REPOSITORY=${SCRIPT_DIRECTORY}/charms
source ${SCRIPT_DIRECTORY}/define-juju.sh
juju status
