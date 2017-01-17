#!/usr/bin/env bash
# Builds the kubernetes project to create the output needed for the Juju Charms.

# The first argument ($1) is the EasyRSA version.
# The second argument ($2) is the flannel version.
# The third argument ($3) is the CNI version.
# The fourth argument ($4) is the etcd version.
# The fifth argument ($5) is the Kubernetes version.

set -o errexit  # Exit when an individual command fails.
set -o pipefail  # The exit status of the last command is returned.
#set -o xtrace  # Print the commands that are executed.

EASYRSA_VERSION=${1:-"3.0.1"}
FLANNEL_VERSION=${2:-"v0.7.0"}
CNI_VERSION=${3:-"v0.4.0"}
ETCD_VERSION=${4:-"v2.3.7"}
KUBE_VERSION=${5:-"v1.5.2"}

SCRIPT_DIR=${PWD}

# Define the get_os function.
source ./utilities.sh

# Create a temporary directory to hold the files.
export TEMPORARY_DIRECTORY=${SCRIPT_DIR}/temp
mkdir -p ${TEMPORARY_DIRECTORY}

# EasyRSA is a collection of scripts, not compiled or built.
./repackage-easyrsa.sh ${EASYRSA_VERSION}

export OS=$(get_os)
export ARCHITECTURES=${ARCHITECTURES:-"amd64"}  #"amd64 arm arm64 ppc64le"
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
