#!/usr/bin/env bash
# Builds the kubernetes project to create the output needed for the Juju Charms.

set -o errexit  # Exit when an individual command fails.
set -o pipefail  # The exit status of the last command is returned.
#set -o xtrace  # Print the commands that are executed.

# The first argument is the EasyRSA version
EASYRSA_VERSION=${1:-"3.0.1"}
# The second argument is the Fflannel version
FLANNEL_VERSION=${2:-"v0.6.2"}
# The third argument is the CNI version.
CNI_VERSION=${3:-"v0.3.0"}
# The fourth argument is the Etcd version.
ETCD_VERSION=${4:-"v2.2.5"}
# The fifth argument is the Kubernetes version.
KUBE_VERSION=${5:-"v1.5.1"}

SCRIPT_DIR=${PWD}

# Define the get_os function.
source ./utilities.sh

# Create a temporary directory to hold the files.
export TEMPORARY_DIRECTORY=${SCRIPT_DIR}/temp
mkdir -p ${TEMPORARY_DIRECTORY}

# EasyRSA is a collection of scripts and not built.
./repackage-easyrsa.sh ${EASYRSA_VERSION}

export OS=$(get_os)
export ARCHITECTURES="amd64 arm64 ppc64le s390x"
for ARCHITECTURE in ${ARCHITECTURES}; do
  export ARCH=${ARCHITECTURE}
  mkdir -p ${TEMPORARY_DIRECTORY}/${OS}/${ARCH}
  # Build the CNI, etcd, and flannel resources.
  ./build-flannel.sh ${FLANNEL_VERSION} ${CNI_VERSION} ${ETCD_VERSION}
done
# Build the cross platform kubernetes binaries.
./build-kubernetes.sh ${KUBE_VERSION}

# Change back to the original directory.
cd ${SCRIPT_DIR}
echo "Removing ${TEMPORARY_DIRECTORY}"
rm -rf ${TEMPORARY_DIRECTORY}
