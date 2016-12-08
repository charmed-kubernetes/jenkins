#!/usr/bin/env bash
# Package the upstream Kubernetes release into Juju Charms resources.
# The first ($1) and only argument should be the url or a path to the release.

set -o errexit  # Exit when an individual command fails.
set -o pipefail  # The exit status of the last command is returned.
#set -o xtrace  # Print the commands that are executed.

echo "The ${0} started at `date`."

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
# Print out the sha256sum and size.
SHA256SUM=`sha256sum ${RELEASE_TAR}`
echo ${SHA256SUM} ${RELEASE_TAR}
ls -hl ${RELEASE_TAR} | cut -d ' ' -f 5

echo "Expanding ${RELEASE_TAR} to ${TEMPORARY_DIRECTORY}"
tar -xvzf ${RELEASE_TAR} -C ${TEMPORARY_DIRECTORY}

if [[ ! -e "${TEMPORARY_DIRECTORY}/kubernetes/version" ]]; then
  echo "Can not determine Kubernetes release." >&2
  exit 2
fi
VERSION=$(cat ${TEMPORARY_DIRECTORY}/kubernetes/version)
echo "Kubernetes release: ${VERSION}"

ARCHITECTURES="amd64 arm64 ppc64le s390x"
# Iterate over the supported architectures.
for ARCH in ${ARCHITECTURES}; do
  ARCH_DIR=${TEMPORARY_DIRECTORY}/${ARCH}
  mkdir -p ${ARCH_DIR}
  TARGET_SERVER_FILE=kubernetes/server/kubernetes-server-linux-${ARCH}.tar.gz
  # Check for this architecture in the archive.
  if ! tar -tzf ${RELEASE_TAR} ${TARGET_SERVER_FILE} 2>/dev/null; then
    echo "Could not find ${ARCH} in ${RELEASE_TAR}"
    continue
  fi
  # Expand the target server file to the architecture directory.
  tar -xvzf ${RELEASE_TAR} -C ${ARCH_DIR} ${TARGET_SERVER_FILE}

  TEMPORARY_SERVER_DIR=${ARCH_DIR}/server
  mkdir -p ${TEMPORARY_SERVER_DIR}
  echo "Expanding ${TARGET_SERVER_FILE} to ${TEMPORARY_SERVER_DIR}"
  tar -xvzf ${ARCH_DIR}/${TARGET_SERVER_FILE} -C ${TEMPORARY_SERVER_DIR}

  cd ${ARCH_DIR}/server/kubernetes/server/bin
  echo "Creating the ${SCRIPT_DIR}/kubernetes-master-${VERSION}-${ARCH}.tar.gz file."
  MASTER_BINS="kube-apiserver kube-controller-manager kubectl kube-dns kube-scheduler"
  tar -cvzf ${SCRIPT_DIR}/kubernetes-master-${VERSION}-${ARCH}.tar.gz ${MASTER_BINS}
  sha256sum ${SCRIPT_DIR}/kubernetes-master-${VERSION}-${ARCH}.tar.gz
  ls -hl ${SCRIPT_DIR}/kubernetes-master-${VERSION}-${ARCH}.tar.gz | cut -d ' ' -f 5

  echo "Creating the ${SCRIPT_DIR}/kubernetes-worker-${VERSION}-${ARCH}.tar.gz file."
  WORKER_BINS="kubectl kubelet kube-proxy"
  tar -cvzf ${SCRIPT_DIR}/kubernetes-worker-${VERSION}-${ARCH}.tar.gz ${WORKER_BINS}
  sha256sum ${SCRIPT_DIR}/kubernetes-worker-${VERSION}-${ARCH}.tar.gz
  ls -hl ${SCRIPT_DIR}/kubernetes-worker-${VERSION}-${ARCH}.tar.gz | cut -d ' ' -f 5

done
# Change back to the original directory.
cd ${SCRIPT_DIR}
# Remove the temporary directory and all files in there.
rm -rf ${TEMPORARY_DIRECTORY}

echo "The ${0} script completed successfully at `date`."
