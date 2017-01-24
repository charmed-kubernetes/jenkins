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

SCRIPT_DIR=${PWD}

# Define the versions of the software to build.
source ./versions.sh

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
  ./build-flannel.sh
done
# Build the cross platform kubernetes binaries.
./build-kubernetes.sh

# Change back to the original directory.
cd ${SCRIPT_DIR}
echo "Removing ${TEMPORARY_DIRECTORY}"
rm -rf ${TEMPORARY_DIRECTORY}
