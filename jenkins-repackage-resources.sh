#!/usr/bin/env bash
# Create the resources for the Canonical Distribution of Kubernetes.

# The first argument ($1) should be the version of easyrsa.
# The second argument ($2) should be the version of flannel.
# The third argument ($4) should be the version of CNI.
# The fourth argument ($5) should be the version of etcd.
# The fifth argument ($1) should be the Kubernetes version.

set -o errexit  # Exit when an individual command fails.
set -o pipefail  # The exit status of the last command is returned.
set -o xtrace  # Print the commands that are executed.

SCRIPT_DIR=${PWD}

EASYRSA_VERSION=${1:-"3.0.1"}
FLANNEL_VERSION=${2:-"v0.6.2"}
CNI_VERSION=${3:-"v0.3.0"}
ETCD_VERSION=${4:-"v2.2.5"}
KUBE_VERSION=${5:-"v1.5.1"}

# Create a temporary directory to hold the files.
export TEMPORARY_DIRECTORY=${SCRIPT_DIR}/temp
mkdir -p ${TEMPORARY_DIRECTORY}

./repackage-easyrsa.sh ${EASYRSA_VERSION}

./repackage-flannel.sh ${FLANNEL_VERSION} ${CNI_VERSION} ${ETCD_VERSION}

./repackage-kubernetes.sh ${KUBE_VERSION}

# Change back to the original directory.
cd ${SCRIPT_DIR}
echo "Removing ${TEMPORARY_DIRECTORY}"
rm -rf ${TEMPORARY_DIRECTORY}
