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

NAMESPACE=${NAMESPACE:-"cs:~containers"}

cd $WORKSPACE

MASTER_CHARM=$(/usr/bin/charm push $PWD/charms/builds/kubernetes-master $NAMESPACE/kubernetes-master | tail -n +1 | head -1 | awk '{print $2}')
WORKER_CHARM=$(/usr/bin/charm push $PWD/charms/builds/kubernetes-worker $NAMESPACE/kubernetes-worker | tail -n +1 | head -1 | awk '{print $2}')
E2E_CHARM=$(/usr/bin/charm push $PWD/charms/builds/kubernetes-e2e $NAMESPACE/kubernetes-e2e | tail -n +1 | head -1 | awk '{print $2}')
LB_CHARM=$(/usr/bin/charm push $PWD/charms/builds/kubeapi-load-balancer $NAMESPACE/kubeapi-load-balancer | tail -n +1 | head -1 | awk '{print $2}')
FLANNEL_CHARM=$(/usr/bin/charm push $PWD/charms/builds/flannel $NAMESPACE/flannel | tail -n +1 | head -1 | awk '{print $2}')
EASY_CHARM=$(/usr/bin/charm push $PWD/charms/builds/easyrsa $NAMESPACE/easyrsa | tail -n +1 | head -1 | awk '{print $2}')
ETCD_CHARM=$(/usr/bin/charm push $PWD/charms/builds/etcd $NAMESPACE/etcd | tail -n +1 | head -1 | awk '{print $2}')

function easyrsa_resource() {
  CHARM=cs:~containers/easyrsa
  RESOURCE_REV=`/usr/bin/charm show ${CHARM} --channel stable resources | grep Revision | awk '{print $2}'`
  echo "easyrsa-${RESOURCE_REV}"
}

function flannel_resource() {
  CHARM=cs:~containers/flannel
  RESOURCE_REV=`/usr/bin/charm show ${CHARM} --channel stable resources | grep Revision | awk '{print $2}'`
  echo "flannel-${RESOURCE_REV}"
}

/usr/bin/charm release ${MASTER_CHARM} --channel edge -r cdk-addons-0 -r kube-apiserver-0 -r kube-controller-manager-0 -r kube-scheduler-0 -r kubectl-0
/usr/bin/charm grant ${MASTER_CHARM} everyone --channel edge

/usr/bin/charm release ${WORKER_CHARM} --channel edge -r cni-0 -r kube-proxy-0 -r kubectl-0 -r kubelet-0
/usr/bin/charm grant ${WORKER_CHARM} everyone --channel edge

RESOURCE=$(easyrsa_resource)
/usr/bin/charm release ${EASY_CHARM} --channel edge -r ${RESOURCE}
/usr/bin/charm grant ${EASY_CHARM} everyone --channel edge

/usr/bin/charm release ${ETCD_CHARM} --channel edge -r etcd-3 -r snapshot-0
/usr/bin/charm grant ${ETCD_CHARM} everyone --channel edge

RESOURCE=$(flannel_resource)
/usr/bin/charm release ${FLANNEL_CHARM} --channel edge -r ${RESOURCE}
/usr/bin/charm grant ${FLANNEL_CHARM} everyone --channel edge

/usr/bin/charm release ${LB_CHARM} --channel edge
/usr/bin/charm grant ${LB_CHARM} everyone --channel edge

BUNDLE_REPOSITORY="https://github.com/juju-solutions/bundle-canonical-kubernetes.git"
git clone ${BUNDLE_REPOSITORY} bundle

bundle/bundle -o ./bundles/cdk-flannel -c edge k8s/cdk cni/flannel
bundle/bundle -o ./bundles/core-flannel -c edge k8s/core cni/flannel

CDK="cs:~containers/bundle/canonical-kubernetes"
CORE="cs:~containers/bundle/kubernetes-core"

PUSH_CMD="/usr/bin/charm push ./bundles/cdk-flannel ${CDK}"
CDK_REVISION=`${PUSH_CMD} | tail -n +1 | head -1 | awk '{print $2}'`
/usr/bin/charm release --channel edge ${CDK_REVISION}
/usr/bin/charm grant --channel edge ${CDK_REVISION} everyone

PUSH_CMD="/usr/bin/charm push ./bundles/core-flannel ${CORE}"
CORE_REVISION=`${PUSH_CMD} | tail -n +1 | head -1 | awk '{print $2}'`
/usr/bin/charm release --channel edge ${CORE_REVISION}
/usr/bin/charm grant --channel edge ${CORE_REVISION} everyone
