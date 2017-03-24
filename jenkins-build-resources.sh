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

# The directory to use for this script, should be WORKSPACE, but can be PWD.
SCRIPT_DIRECTORY=${WORKSPACE:-${PWD}}

# Define the versions of the software to build.
source ${SCRIPT_DIRECTORY}/versions.sh

# Define the get_os function.
source ${SCRIPT_DIRECTORY}/utilities.sh

# Create a temporary directory to hold the files.
export TEMPORARY_DIRECTORY=${SCRIPT_DIRECTORY}/temp
mkdir -p ${TEMPORARY_DIRECTORY}

# EasyRSA is a collection of scripts, not compiled or built.
${SCRIPT_DIRECTORY}/repackage-easyrsa.sh ${EASYRSA_VERSION}

export OS=$(get_os)
export ARCHITECTURES=${ARCHITECTURES:-"amd64"}  #"amd64 arm arm64 ppc64le"
for ARCHITECTURE in ${ARCHITECTURES}; do
  export ARCH=${ARCHITECTURE}
  mkdir -p ${TEMPORARY_DIRECTORY}/${OS}/${ARCH}
  # Build the CNI, etcd, and flannel resources.
  ${SCRIPT_DIRECTORY}/build-flannel.sh
done
# Build the cross platform kubernetes binaries.
${SCRIPT_DIRECTORY}/build-kubernetes.sh

# Change back to the original directory.
cd ${SCRIPT_DIRECTORY}
echo "Removing ${TEMPORARY_DIRECTORY}"
rm -rf ${TEMPORARY_DIRECTORY}
