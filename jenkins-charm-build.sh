#!/usr/bin/env bash
# Runs the charm build for the Canonical Kubernetes charms.

set -o errexit  # Exit when an individual command fails.
set -o nounset  # Exit when undeclaried variables are used.
set -o pipefail  # The exit status of the last command is returned.
set -o xtrace  # Print the commands that are executed.

# The path to the archive of the JUJU_DATA directory for the specific cloud.
JUJU_DATA_TAR="/var/lib/jenkins/juju/juju_${CLOUD}.tar.gz"
# Uncompress the file that contains the Juju data to the workspace directory.
tar -xvzf ${JUJU_DATA_TAR} -C ${WORKSPACE}

# Set the JUJU_DATA directory for this jenkins workspace.
export JUJU_DATA=${WORKSPACE}/juju
export JUJU_REPOSITORY=${WORKSPACE}/charms

SCRIPT_DIR=${PWD}

# Clone the charm repositories.
git clone https://github.com/juju-solutions/layer-easyrsa.git 
git clone https://github.com/juju-solutions/layer-etcd.git
git clone https://github.com/juju-solutions/charm-flannel.git
# The kubernetes repository holds several charm layers.
git clone https://github.com/juju-solutions/kubernetes.git
cd kubernetes
# Checkout the right branch.
git checkout -f master-node-split

# Build the charms with no local layers
CHARM_BUILD_CMD="charm build -r --no-local-layers" 
in-charmbox "cd workspace/layer-easyrsa && ${CHARM_BUILD_CMD}"
in-charmbox "cd workspace/layer-etcd && ${CHARM_BUILD_CMD}"
in-charmbox "cd workspace/charm-flannel && ${CHARM_BUILD_CMD}"
in-charmbox "cd workspace/kubernetes/cluster/juju/layers/kubeapi-loadbalancer && ${CHARM_BUILD_CMD}"
in-charmbox "cd workspace/kubernetes/cluster/juju/layers/kubernetes-e2e && ${CHARM_BUILD_CMD}"
in-charmbox "cd workspace/kubernetes/cluster/juju/layers/kubernetes-master && ${CHARM_BUILD_CMD}"
in-charmbox "cd workspace/kubernetes/cluster/juju/layers/kubermetes-worker && ${CHARM_BUILD_CMD}"

echo "Deploy the locally built charms."

echo "Relate the charms."

echo "Attach the resources."
