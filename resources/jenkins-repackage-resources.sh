#!/usr/bin/env bash
# Create the resources for the Canonical Distribution of Kubernetes.

# The first argument ($1) should be the version of easyrsa.
# The second argument ($2) should be the version of flannel.
# The third argument ($4) should be the version of CNI.
# The fourth argument ($5) should be the version of etcd.
# The fifth argument ($1) should be the Kubernetes version.

set -o errexit  # Exit when an individual command fails.
set -o pipefail  # The exit status of the last command is returned.
#set -o xtrace  # Print the commands that are executed.

SCRIPT_DIR=${PWD}

# Define the get_os function.
source ./utilities.sh

# Create a temporary directory to hold the files.
export TEMPORARY_DIRECTORY=${SCRIPT_DIR}/temp
mkdir -p ${TEMPORARY_DIRECTORY}

# EasyRSA is a collection of scripts, not compiled or built.
resources/repackage-easyrsa.sh

export OS=$(get_os)
export ARCHITECTURES=${ARCHITECTURES:-"amd64 arm64"}  #"amd64 arm arm64 ppc64le"
for ARCHITECTURE in ${ARCHITECTURES}; do
  export ARCH=${ARCHITECTURE}
  mkdir -p ${TEMPORARY_DIRECTORY}/${OS}/${ARCH}
  # Repackage the CNI, etcd, and flannel resources.
  resources/repackage-flannel.sh
done

# Change back to the original directory.
cd ${SCRIPT_DIR}
echo "Removing ${TEMPORARY_DIRECTORY}"
rm -rf ${TEMPORARY_DIRECTORY}
