#!/usr/bin/env bash
# Clone the kubernetes layers and build the charms.

set -o errexit  # Exit when an individual command fails.
set -o pipefail  # The exit status of the last command is returned.
set -o xtrace  # Print the commands that are executed.

echo "${0} started at `date`."

SCRIPT_DIR=${PWD}

# Clone the charm repositories to the current directory.
git clone https://github.com/juju-solutions/layer-easyrsa.git 
git clone https://github.com/juju-solutions/layer-etcd.git
git clone https://github.com/juju-solutions/charm-flannel.git
# The kubernetes repository contains several charm layers.
git clone https://github.com/juju-solutions/kubernetes.git
cd kubernetes
# Checkout the right branch.
git checkout -f master-node-split

# Define the juju and in-charmbox functions.
source ./define-juju.sh

# Build the charms with no local layers
CHARM_BUILD_CMD="charm build -r --no-local-layers" 
in-charmbox "cd workspace/layer-easyrsa && ${CHARM_BUILD_CMD}"
in-charmbox "cd workspace/layer-etcd && ${CHARM_BUILD_CMD}"
in-charmbox "cd workspace/charm-flannel && ${CHARM_BUILD_CMD}"
in-charmbox "cd workspace/kubernetes/cluster/juju/layers/kubeapi-loadbalancer && ${CHARM_BUILD_CMD}"
in-charmbox "cd workspace/kubernetes/cluster/juju/layers/kubernetes-e2e && ${CHARM_BUILD_CMD}"
in-charmbox "cd workspace/kubernetes/cluster/juju/layers/kubernetes-master && ${CHARM_BUILD_CMD}"
in-charmbox "cd workspace/kubernetes/cluster/juju/layers/kubermetes-worker && ${CHARM_BUILD_CMD}"

echo "Build successfull the charms are available at ${SCRIPT_DIR}/charms"

echo "${0} completed successfully at `date`."
