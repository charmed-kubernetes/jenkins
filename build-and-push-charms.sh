#!/usr/bin/env bash
# Runs the charm build for the Canonical Kubernetes charms.

set -o errexit  # Exit when an individual command fails.
#set -o nounset  # Exit when undeclaried variables are used.
set -o pipefail  # The exit status of the last command is returned.
set -o xtrace  # Print the commands that are executed.

# banana
WORKSPACE=$PWD

source ./define-juju.sh

# The directory to use for this script, should be WORKSPACE, but can be PWD.
SCRIPT_DIRECTORY=${WORKSPACE:-${PWD}}

echo "${0} started at `date`."

SCRIPT_DIR=${PWD}

# Set the Juju envrionment variables for this script.
export JUJU_DATA=/home/charles/work/.juju
export JUJU_REPOSITORY=${SCRIPT_DIRECTORY}/charms


# Define the juju and in-charmbox functions.
source ./define-juju.sh

# Clone the charm repositories to the current directory.
if [ ! -d "$PWD/layer-easyrsa" ]; then
  git clone https://github.com/juju-solutions/layer-easyrsa.git
fi

if [ ! -d "$PWD/layer-etcd" ]; then
  git clone https://github.com/juju-solutions/layer-etcd.git
fi

if [ ! -d "$PWD/charm-flannel" ]; then
  git clone https://github.com/juju-solutions/charm-flannel.git
fi

# If the kubernetes repostory environment variable is defined use it, otherwise use upstream.
KUBERNETES_REPOSITORY=${KUBERNETES_REPOSITORY:-"https://github.com/juju-solutions/kubernetes.git"}

if [ ! -d kubernetes ]; then
  git clone ${KUBERNETES_REPOSITORY} kubernetes
fi

# The kubernetes repository contains several charm layers.
cd kubernetes

# If the kubernetes branch environment variable is defined use it, otherwise build from master.
KUBERNETES_BRANCH=${KUBERNETES_BRANCH:-"master"}

# Checkout the right branch.
git checkout -f ${KUBERNETES_BRANCH}

cd ${SCRIPT_DIR}

# Change the ownership of the charms directory to ubuntu user.
#in-charmbox "sudo chown -R ubuntu:ubuntu /home/ubuntu/charms"

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

echo "Build successfull the charms are available at ${SCRIPT_DIR}/charms/builds"

echo "${0} completed successfully at `date`."

NAMESPACE=${NAMESPACE:-"cs:~containers"}

cd $WORKSPACE

charm push $PWD/charms/builds/kubernetes-master $NAMESPACE/kubernetes-master
charm push $PWD/charms/builds/kubernetes-worker $NAMESPACE/kubernetes-worker
charm push $PWD/charms/builds/kubernetes-e2e $NAMESPACE/kubernetes-e2e
charm push $PWD/charms/builds/kubeapi-load-balancer $NAMESPACE/kubeapi-load-balancer
charm push $PWD/charms/builds/flannel $NAMESPACE/flannel
charm push $PWD/charms/builds/easyrsa $NAMESPACE/easyrsa
charm push $PWD/charms/builds/etcd $NAMESPACE/etcd

