#!/usr/bin/env bash
# Package the upstream Kubernetes release into Juju Charms resources.
# The first ($1) and only argument should be the url or path to the archive.

set -o errexit  # Exit when an individual command fails.
set -o pipefail  # The exit status of the last command is returned.
#set -o xtrace  # Print the commands that are executed.

echo "${0} started at `date`."

source ./util.sh

SCRIPT_DIR=${PWD}

# Create a temporary directory to hold the files.
TEMPORARY_DIRECTORY=${SCRIPT_DIR}/temp
mkdir -p ${TEMPORARY_DIRECTORY}

if [[ ${1} == "http"* ]]; then
  # -L Follow location redirects
  # -f fail silently
  curl -f -L --retry 3 ${1} -o ${TEMPORARY_DIRECTORY}/kubernetes.tar.gz
  RELEASE_TAR=${TEMPORARY_DIRECTORY}/kubernetes.tar.gz
else
  RELEASE_TAR=${1}
fi
# Print out the size and sha256 hash sum of the release archive.
echo "$(ls -hl ${RELEASE_TAR} | cut -d ' ' -f 5) $(basename ${RELEASE_TAR})"
echo "$(sha256sum_file ${RELEASE_TAR}) $(basename ${RELEASE_TAR})"

echo "Expanding ${RELEASE_TAR} to ${TEMPORARY_DIRECTORY}"
tar -xvzf ${RELEASE_TAR} -C ${TEMPORARY_DIRECTORY}
KUBE_ROOT=${TEMPORARY_DIRECTORY}/kubernetes

if [[ ! -e "${KUBE_ROOT}/version" ]]; then
  echo "Can not determine Kubernetes release." >&2
  exit 2
fi
VERSION=$(cat ${KUBE_ROOT}/version)
echo "Found version: ${VERSION}"

export KUBERNETES_SKIP_CONFIRM=Y
export KUBERNETES_DOWNLOAD_TESTS=Y
# Use the upstream utility for downloading binaries.
${KUBE_ROOT}/cluster/get-kube-binaries.sh
# This script does not download architectures other than the host system.
# TODO figure out how to download different architectures.
ARCH=$(get_arch)
OS=$(get_os)

E2E_DIRECTORY=${KUBE_ROOT}/platforms/${OS}/${ARCH}
E2E_ARCHIVE=${SCRIPT_DIR}/e2e-${VERSION}-${ARCH}.tar.gz
echo "Creating the ${E2E_ARCHIVE} file."
E2E_FILES="kubectl ginkgo e2e.test e2e_node.test"
create_archive ${E2E_DIRECTORY} ${E2E_ARCHIVE} "${E2E_FILES}"

SERVER_FILE=${KUBE_ROOT}/server/kubernetes-server-${OS}-${ARCH}.tar.gz
# If the server file does not exist the get-kube-binaries.sh did not work.
if [[ ! -e ${SERVER_FILE} ]]; then
  echo "${SERVER_FILE} does not exist!" >&2
  exit 3
fi
# Print out the size and sha256 hash sum of the server file.
echo "$(ls -hl ${SERVER_FILE} | cut -d ' ' -f 5) $(basename ${SERVER_FILE})"
echo "$(sha256sum_file ${SERVER_FILE}) $(basename ${SERVER_FILE})"

# Expand the server file archive to get the master binaries.
tar -xvzf ${SERVER_FILE} -C ${TEMPORARY_DIRECTORY}
# The server directory is where the master and server binaries are kept. 
SERVER_DIRECTORY=${KUBE_ROOT}/server/bin

MASTER_ARCHIVE=${SCRIPT_DIR}/kubernetes-master-${VERSION}-${ARCH}.tar.gz
echo "Creating the ${MASTER_ARCHIVE} file."
MASTER_FILES="kube-apiserver kube-controller-manager kubectl kube-dns kube-scheduler"
create_archive ${SERVER_DIRECTORY} ${MASTER_ARCHIVE} "${MASTER_FILES}"

WORKER_ARCHIVE=${SCRIPT_DIR}/kubernetes-worker-${VERSION}-${ARCH}.tar.gz
echo "Creating the ${WORKER_ARCHIVE} file."
WORKER_FILES="kubectl kubelet kube-proxy"
create_archive ${SERVER_DIRECTORY} ${WORKER_ARCHIVE} "${WORKER_FILES}"

# Change back to the original directory.
cd ${SCRIPT_DIR}
echo "Removing ${TEMPORARY_DIRECTORY}"
rm -rf ${TEMPORARY_DIRECTORY}
echo ""
echo "${0} completed successfully at `date`."
