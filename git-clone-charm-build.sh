#!/usr/bin/env bash
# Clone the kubernetes layers and build the charms.

set -o errexit  # Exit when an individual command fails.
set -o pipefail  # The exit status of the last command is returned.
set -o xtrace  # Print the commands that are executed.

echo "${0} started at `date`."

SCRIPT_DIR=${PWD}

# Define the juju and in-charmbox functions.
source ./define-juju.sh

# Clone the charm repositories to the current directory.
git clone https://github.com/juju-solutions/layer-easyrsa.git 
git clone https://github.com/juju-solutions/layer-etcd.git
git clone https://github.com/juju-solutions/charm-flannel.git

# If the kubernetes repostory environment variable is defined use it, otherwise use upstream.
KUBERNETES_REPOSITORY=${KUBERNETES_REPOSITORY:-https://github.com/kubernetes/kubernetes.git}
# The kubernetes repository contains several charm layers.
git clone ${KUBERNETES_REPOSITORY} kubernetes
cd kubernetes
# If the kubernetes branch environment variable is defined use it, otherwise build from master.
KUBERNETES_BRANCH=${KUBERNETES_BRANCH:-master}
# Checkout the right branch.
git checkout -f ${KUBERNETES_BRANCH}

cd ${SCRIPT_DIR}

# Change the ownership of the charms directory to ubuntu user.
in-charmbox "sudo chown -R ubuntu:ubuntu /home/ubuntu/charms"
# Build the charms with no local layers
CHARM_BUILD_CMD="charm build -r --no-local-layers --force" 
in-charmbox "cd workspace/layer-easyrsa && ${CHARM_BUILD_CMD}"
in-charmbox "cd workspace/layer-etcd && ${CHARM_BUILD_CMD}"
in-charmbox "cd workspace/charm-flannel && ${CHARM_BUILD_CMD}"
in-charmbox "cd workspace/kubernetes/cluster/juju/layers/kubeapi-load-balancer && ${CHARM_BUILD_CMD}"
in-charmbox "cd workspace/kubernetes/cluster/juju/layers/kubernetes-e2e && ${CHARM_BUILD_CMD}"
in-charmbox "cd workspace/kubernetes/cluster/juju/layers/kubernetes-master && ${CHARM_BUILD_CMD}"
in-charmbox "cd workspace/kubernetes/cluster/juju/layers/kubernetes-worker && ${CHARM_BUILD_CMD}"
# Change the ownership of the charms directory to ubuntu user.
in-charmbox "sudo chown -R ubuntu:ubuntu /home/ubuntu/charms"

source ./utilities.sh
create_archive charms/builds ${SCRIPT_DIR}/easyrsa.tar.gz easyrsa
create_archive charms/builds ${SCRIPT_DIR}/etcd.tar.gz etcd
create_archive charms/builds ${SCRIPT_DIR}/flannel.tar.gz flannel
create_archive charms/builds ${SCRIPT_DIR}/kubeapi-load-balancer.tar.gz kubeapi-load-balancer
create_archive charms/builds ${SCRIPT_DIR}/kubernetes-e2e.tar.gz kubernetes-e2e
create_archive charms/builds ${SCRIPT_DIR}/kubernetes-master.tar.gz kubernetes-master
create_archive charms/builds ${SCRIPT_DIR}/kubernetes-worker.tar.gz kubernetes-worker

echo "Build successfull the charms are available at ${SCRIPT_DIR}/charms"

echo "${0} completed successfully at `date`."
