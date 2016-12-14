#!/usr/bin/env bash
# Package the upstream Kubernetes release into Juju Charms resources.
# The first ($1) and only argument should be the url or path to the archive.

set -o errexit  # Exit when an individual command fails.
set -o pipefail  # The exit status of the last command is returned.
#set -o xtrace  # Print the commands that are executed.

echo "${0} started at `date`."

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

# Get the function definitions for os and architecture detection.
source ./utilities.sh

ARCH=$(get_arch)
OS=$(get_os)

ARCHITECTURES="amd64 arm64 ppc64le s390x"
# Iterate over the supported architectures.
for ARCH in ${ARCHITECTURES}; do
  SERVER_FILE=kubernetes/server/kubernetes-server-${OS}-${ARCH}.tar.gz
  # Check for this architecture in the archive.
  if ! tar -tzf ${RELEASE_TAR} ${SERVER_FILE} 2>/dev/null; then
    echo "Could not find ${ARCH} in ${RELEASE_TAR}"
    continue
  fi
  ARCH_DIR=${TEMPORARY_DIRECTORY}/${ARCH}
  mkdir -p ${ARCH_DIR}
  # Expand the target server file to the architecture directory.
  tar -xvzf ${RELEASE_TAR} -C ${ARCH_DIR} ${SERVER_FILE}

  SERVER_DIRECTORY=${ARCH_DIR}/server
  mkdir -p ${SERVER_DIRECTORY}
  echo "Expanding ${SERVER_FILE} to ${SERVER_DIRECTORY}"
  tar -xvzf ${ARCH_DIR}/${SERVER_FILE} -C ${SERVER_DIRECTORY}
  # The bin directory is where the master and server binaries are kept.
  SERVER_BIN_DIRECTORY=${ARCH_DIR}/server/kubernetes/server/bin
  
  MASTER_ARCHIVE=${SCRIPT_DIR}/kubernetes-master-${VERSION}-${ARCH}.tar.gz
  echo "Creating the ${MASTER_ARCHIVE} file."
  MASTER_FILES="kube-apiserver kube-controller-manager kubectl kube-dns kube-scheduler"
  create_archive ${SERVER_BIN_DIRECTORY} ${MASTER_ARCHIVE} "${MASTER_FILES}"
  
  WORKER_ARCHIVE=${SCRIPT_DIR}/kubernetes-worker-${VERSION}-${ARCH}.tar.gz
  echo "Creating the ${WORKER_ARCHIVE} file."
  WORKER_FILES="kubectl kubelet kube-proxy"
  create_archive ${SERVER_BIN_DIRECTORY} ${WORKER_ARCHIVE} "${WORKER_FILES}"
done
# Change back to the original directory.
cd ${SCRIPT_DIR}
echo "Removing ${TEMPORARY_DIRECTORY}"
rm -rf ${TEMPORARY_DIRECTORY}
echo ""
echo "${0} completed successfully at `date`."
