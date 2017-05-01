#!/usr/bin/env bash
# Runs the charm build for the Canonical Kubernetes charms.

set -o errexit  # Exit when an individual command fails.
set -o nounset  # Exit when undeclaried variables are used.
set -o pipefail  # The exit status of the last command is returned.
set -o xtrace  # Print the commands that are executed.

source ./define-juju.sh

# The directory to use for this script, should be WORKSPACE, but can be PWD.
WORKSPACE=${WORKSPACE:-${PWD}}

echo "${0} started at `date`."

# Set the Juju envrionment variables for this script.
export JUJU_REPOSITORY=${WORKSPACE}/charms

# The cloud is an option for this script, default to gce.
CLOUD=${CLOUD:-"gce"}
# The directory to use for this script, should be WORKSPACE, but can be PWD.
WORKSPACE=${WORKSPACE:-${PWD}}

set +u
if [ -z ${JUJU_DATA} ]; then
  export JUJU_DATA=${WORKSPACE}/juju
  # The path to the archive of the JUJU_DATA directory for the specific cloud.
  JUJU_DATA_TAR="/var/lib/jenkins/juju/juju_${CLOUD}.tar.gz"
  # Uncompress the file that contains the Juju data to the workspace directory.
  tar -xvzf ${JUJU_DATA_TAR} -C ${WORKSPACE}
fi
set -u

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

cd ${WORKSPACE}

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

echo "Build successfull the charms are available at ${WORKSPACE}/charms/builds"

echo "${0} completed successfully at `date`."

NAMESPACE=${NAMESPACE:-"cs:~containers"}

cd $WORKSPACE

/snap/bin/charm push $PWD/charms/builds/kubernetes-master $NAMESPACE/kubernetes-master
/snap/bin/charm push $PWD/charms/builds/kubernetes-worker $NAMESPACE/kubernetes-worker
/snap/bin/charm push $PWD/charms/builds/kubernetes-e2e $NAMESPACE/kubernetes-e2e
/snap/bin/charm push $PWD/charms/builds/kubeapi-load-balancer $NAMESPACE/kubeapi-load-balancer
/snap/bin/charm push $PWD/charms/builds/flannel $NAMESPACE/flannel
/snap/bin/charm push $PWD/charms/builds/easyrsa $NAMESPACE/easyrsa
/snap/bin/charm push $PWD/charms/builds/etcd $NAMESPACE/etcd
