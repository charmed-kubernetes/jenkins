#!/usr/bin/env bash
# Uploads the kubernetes charms to the Juju charm store.

set -o errexit  # Exit when an individual command fails.
set -o pipefail  # The exit status of the last command is returned.
set -o xtrace  # Print the commands that are executed.

JUJU_REPOSITORY=${1:-$JUJU_REPOSITORY}
RESOURCES_DIRECTORY=${2:-"resources"}
ARCH=${ARCH:-"amd64"}
CHANNEL=${CHANNEL:-"edge"}

if [ ! -d ${RESOURCES_DIRECTORY} ]; then
  echo "Invalid resources directory ${RESOURCES_DIRECTORY}"
  exit 1
fi

# Etcd has a snapshot resource that should always be a zero byte file.
URL=https://api.jujucharms.com/charmstore/v5/~containers/etcd/resource/snapshot/0
wget ${URL} -O ${RESOURCES_DIRECTORY}/etcd_snapshot.tar.gz

# Get the resource path names.
E2E_RESOURCE=$(ls -1 ${RESOURCES_DIRECTORY}/e2e-*-${ARCH}.tar.gz)
EASYRSA_RESOURCE=$(ls -1 ${RESOURCES_DIRECTORY}/easyrsa-resource-*.tgz)
ETCD_RESOURCE="${RESOURCES_DIRECTORY}/etcd_snapshot.tar.gz"
FLANNEL_RESOURCE=$(ls -1 ${RESOURCES_DIRECTORY}/flannel-resource-*-${ARCH}.tar.gz)
MASTER_RESOURCE=$(ls -1 ${RESOURCES_DIRECTORY}/kubernetes-master-*-${ARCH}.tar.gz)
WORKER_RESOURCE=$(ls -1 ${RESOURCES_DIRECTORY}/kubernetes-worker-*-${ARCH}.tar.gz)

#TODO add the cs:~containers/charm-name to the push command.

function charm_push_release () {
  local charm_directory=${1}
  local resource_name=${2}
  local resource_path=${3}
  # Create the charm push command with the charm directory.
  local push_cmd="charm push ${charm_directory}"
  # Append the resource information if provided.
  if [ -n "${resource_name}" ] && [ -n "${resource_path}" ]; then
    push_cmd="${push_cmd} --resource ${resource_name}=${resource_path}"
  fi
  local push=$(${push_cmd})
  echo ${push}
  # Parse the charm url from the output.
  local url=$(echo ${push} | grep 'url:' | cut -d ' ' -f 2)
  local release_cmd="charm release ${url} --channel ${CHANNEL}"
  if [ -n "${resource_name}" ] && [ -n "${resource_path}" ]; then
    # Parse the resource id from the output.
    local id=$(echo ${push} | grep 'Uploaded' | cut -d ' ' -f 8)
    release_cmd="${release_cmd} --resource ${id}"
  fi
  # Release the charm to the charm store.
  local release=$(${release_cmd})
  echo ${release}
}

charm_push_release ${JUJU_REPOSITORY}/builds/easyrsa easyrsa ${EASYRSA_RESOURCE}
charm_push_release ${JUJU_REPOSITORY}/builds/etcd snapshot ${ETCD_RESOURCE}
charm_push_release ${JUJU_REPOSITORY}/builds/flannel flannel ${FLANNEL_RESOURCE}
charm_push_release ${JUJU_REPOSITORY}/builds/kubeapi-load-balancer
charm_push_release ${JUJU_REPOSITORY}/builds/kubernetes-e2e e2e_${ARCH} ${E2E_RESOURCE}
charm_push_release ${JUJU_REPOSITORY}/builds/kubernetes-master kubernetes ${MASTER_RESOURCE}
charm_push_release ${JUJU_REPOSITORY}/builds/kubernetes-worker kubernetes ${WORKER_RESOURCE}
