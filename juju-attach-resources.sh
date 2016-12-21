#!/usr/bin/env bash
# Attaches local resources to Kubernetes charms.

# The first argument is the _relative_ resources directory.

set -o errexit  # Exit when an individual command fails.
set -o pipefail  # The exit status of the last command is returned.
set -o xtrace  # Print the commands that are executed.

echo "${0} started at `date`."

RESOURCES_DIRECTORY=${1:-"resources"}

ARCH=${ARCH:-"amd64"}

# Get the _relative_ resource names.
E2E_RESOURCE=$(ls -1 ${RESOURCES_DIRECTORY}/e2e-*-${ARCH}.tar.gz)
EASYRSA_RESOURCE=$(ls -1 ${RESOURCES_DIRECTORY}/easyrsa-resource-*.tgz)
FLANNEL_RESOURCE=$(ls -1 ${RESOURCES_DIRECTORY}/flannel-resource-*-${ARCH}.tar.gz)
MASTER_RESOURCE=$(ls -1 ${RESOURCES_DIRECTORY}/kubernetes-master-*-${ARCH}.tar.gz)
WORKER_RESOURCE=$(ls -1 ${RESOURCES_DIRECTORY}/kubernetes-worker-*-${ARCH}.tar.gz)

# Define the juju functions.
source ./define-juju.sh

# Attach the resources using the workspace directory inside the container.
juju attach easyrsa easyrsa=/home/ubuntu/workspace/${EASYRSA_RESOURCE}
juju attach flannel flannel=/home/ubuntu/workspace/${FLANNEL_RESOURCE}
juju attach kubernetes-e2e e2e_${ARCH}=/home/ubuntu/workspace/${E2E_RESOURCE}
juju attach kubernetes-master kubernetes=/home/ubuntu/workspace/${MASTER_RESOURCE}
juju attach kubernetes-worker kubernetes=/home/ubuntu/workspace/${WORKER_RESOURCE}

echo "${0} completed successfully at `date`."
