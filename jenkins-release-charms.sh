#!/usr/bin/env bash
# Push the kubernetes charm code, release the charms and grant everyone access.

set -o errexit  # Exit when an individual command fails.
set -o pipefail  # The exit status of the last command is returned.
set -o xtrace  # Print the commands that are executed.

SCRIPT_DIR="$( cd "$( dirname "${0}" )" && pwd )"
if [[ -z "${WORKSPACE}" ]]; then
  export WORKSPACE=${PWD}
fi
ID=${1}
CHANNEL=${2}

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

# Expand all the charm archives to the charms/builds directory.
CHARMS_BUILDS=${JUJU_REPOSITORY}/builds
tar -xzf ${CHARMS_BUILDS}/easyrsa.tar.gz -C ${CHARMS_BUILDS}
tar -xzf ${CHARMS_BUILDS}/etcd.tar.gz -C ${CHARMS_BUILDS}
tar -xzf ${CHARMS_BUILDS}/flannel.tar.gz -C ${CHARMS_BUILDS}
tar -xzf ${CHARMS_BUILDS}/kubeapi-load-balancer.tar.gz -C ${CHARMS_BUILDS}
tar -xzf ${CHARMS_BUILDS}/kubernetes-e2e.tar.gz -C ${CHARMS_BUILDS}
tar -xzf ${CHARMS_BUILDS}/kubernetes-master.tar.gz -C ${CHARMS_BUILDS}
tar -xzf ${CHARMS_BUILDS}/kubernetes-worker.tar.gz -C ${CHARMS_BUILDS}
ls -al ${CHARMS_BUILDS}/*

CHANNEL_FLAG=""
# The channel is optional, when a channel is specified add the channel flag.
if [[ -n "${CHANNEL}" ]]; then
  CHANNEL_FLAG="--channel=${CHANNEL}"
fi

ARCH=${ARCH:-"amd64"}
# The resources must be in the current directory.
E2E_RESOURCE=$(ls -1 e2e-*-${ARCH}.tar.gz)
EASYRSA_RESOURCE=$(ls -1 easyrsa-resource-*.tgz)
FLANNEL_RESOURCE=$(ls -1 flannel-resource-*-${ARCH}.tar.gz)
MASTER_RESOURCE=$(ls -1 kubernetes-master-*-${ARCH}.tar.gz)
WORKER_RESOURCE=$(ls -1 kubernetes-worker-*-${ARCH}.tar.gz)

# Get the charm identifiers for each charm, none of them have a series.
E2E=$(charm_id ${ID} "" kubernete-e2e)
EASYRSA=$(charm_id ${ID} "" easyrsa)
ETCD=$(charm_id ${ID} "" etcd)
FLANNEL=$(charm_id ${ID} "" flannel)
MASTER=$(charm_id ${ID} "" kubernetes-master)
WORKER=$(charm_id ${ID} "" kubernetes-worker)

CONTAINER_PATH=/home/ubuntu/workspace
# Attach the resources using the workspace directory inside the container.
charm attach ${E2E} ${CHANNEL_FLAG} e2e_${ARCH}=${CONTAINER_PATH}/${E2E_RESOURCE}
charm attach ${EASYRSA} ${CHANNEL_FLAG} easyrsa=${CONTAINER_PATH}/${EASYRSA_RESOURCE}
charm attach ${FLANNEL} ${CHANNEL_FLAG} flannel=${CONTAINER_PATH}/${FLANNEL_RESOURCE}
# The etcd charm has a snapshot resource, that is not uploaded to the charm store.
charm attach ${MASTER} ${CHANNEL_FLAG} kubernetes=${CONTAINER_PATH}/${MASTER_RESOURCE}
charm attach ${WORKER} ${CHANNEL_FLAG} kubernetes=${CONTAINER_PATH}/${WORKER_RESOURCE}

E2E_RESOURCES=$(charm_resources ${E2E} ${CHANNEL})
charm_push_release ${CHARM_BUILDS}/kubernetes-e2e ${E2E} ${CHANNEL} "${E2E_RESOURCES}"
EASYRSA_RESOURCES=$(charm_resources ${EASYRSA} ${CHANNEL})
charm_push_release ${CHARM_BUILDS}/easyrsa ${EASYRSA} ${CHANNEL} "${EASYRSA_RESOURCES}"
ETCD_RESOURCES=$(charm_resources ${ETCD} ${CHANNEL})
charm_push_release ${CHARM_BUILDS}/etcd ${ETCD} ${CHANNEL} "${ETCD_RESOURCES}"
FLANNEL_RESOURCES=$(charm_resources ${FLANNEL} ${CHANNEL})
charm_push_release ${CHARM_BUILDS}/flannel ${FLANNEL} ${CHANNEL} "${FLANNEL_RESOURCES}"
MASTER_RESOURCES=$(charm_resources ${MASTER} ${CHANNEL})
charm_push_release ${CHARM_BUILDS}/kubernetes-master ${MASTER} ${CHANNEL} "${MASTER_RESOURCES}"
WORKER_RESOURCES=$(charm_resources ${WORKER} ${CHANNEL})
charm_push_release ${CHARM_BUILDS}/kubernetes-worker ${WORKER} ${CHANNEL} "${WORKER_RESOURCES}"
