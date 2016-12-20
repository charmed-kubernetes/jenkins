#!/usr/bin/env bash
# Create the resources for the Canonical Distribution of Kubernetes.

# The first argument ($1) should be the Kubernetes version.
# The second argument ($2) should be the version of flannel.
# The third argument ($3) should be the version of easyrsa.
# The fourth argument ($4) should be the version of CNI.
# The fifth argument ($5) should be the version of etcd.

set -o errexit  # Exit when an individual command fails.
set -o pipefail  # The exit status of the last command is returned.
#set -o xtrace  # Print the commands that are executed.

echo "${0} started at `date`."

SCRIPT_DIR=${PWD}

KUBE_VERSION=${1:-"v1.5.1"}
FLANNEL_VERSION=${2:-"v0.6.2"}
EASYRSA_VERSION=${3:-"3.0.1"}
CNI_VERSION=${4:-"v0.3.0"}
ETCD_VERSION=${5:-"v2.2.5"}

# Get the function definitions for os and architecture detection.
source ./utilities.sh

ARCH=$(get_arch)
OS=$(get_os)

# Create a temporary directory to hold the files.
TEMPORARY_DIRECTORY=${SCRIPT_DIR}/temp
mkdir -p ${TEMPORARY_DIRECTORY}

CNI_URL=https://github.com/containernetworking/cni/releases/download/${CNI_VERSION}/cni-${CNI_VERSION}.tgz
CNI_ARCHIVE=${TEMPORARY_DIRECTORY}/cni.tgz
download ${CNI_URL} ${CNI_ARCHIVE}
tar -xzvf ${CNI_ARCHIVE} -C ${TEMPORARY_DIRECTORY}

EASYRSA_URL=https://github.com/OpenVPN/easy-rsa/releases/download/${EASYRSA_VERSION}/EasyRSA-${EASYRSA_VERSION}.tgz
# Copy the easyrsa archive to the script directory because it is not modified.
EASYRSA_ARCHIVE=${SCRIPT_DIR}/EasyRSA-${EASYRSA_VERSION}.tgz
echo "Creating the ${EASYRSA_ARCHIVE} file."
download ${EASYRSA_URL} ${EASYRSA_ARCHIVE}

ETCD_URL=https://github.com/coreos/etcd/releases/download/${ETCD_VERSION}/etcd-${ETCD_VERSION}-${OS}-${ARCH}.tar.gz
ETCD_ARCHIVE=${TEMPORARY_DIRECTORY}/etcd.tar.gz
download ${ETCD_URL} ${ETCD_ARCHIVE}
tar -xzvf ${ETCD_ARCHIVE} -C ${TEMPORARY_DIRECTORY}
ETCDCTL=${TEMPORARY_DIRECTORY}/etcd-${ETCD_VERSION}-${OS}-${ARCH}/etcdctl
# Copy the etcdctl binary to the temporary directory for the flannel resource.
cp -v ${ETCDCTL} ${TEMPORARY_DIRECTORY}/

FLANNEL_URL=https://github.com/coreos/flannel/releases/download/${FLANNEL_VERSION}/flannel-${FLANNEL_VERSION}-${OS}-${ARCH}.tar.gz
FLANNEL_TAR_GZ=${TEMPORARY_DIRECTORY}/flannel.tar.gz
download ${FLANNEL_URL} ${FLANNEL_TAR_GZ}
tar -xvzf ${FLANNEL_TAR_GZ} -C ${TEMPORARY_DIRECTORY}

FLANNEL_ARCHIVE=${SCRIPT_DIR}/flannel-resource-${FLANNEL_VERSION}-${OS}-${ARCH}.tar.gz
echo "Creating the ${FLANNEL_ARCHIVE} file."
FLANNEL_FILES="bridge etcdctl flannel flanneld host-local"
create_archive ${TEMPORARY_DIRECTORY} ${FLANNEL_ARCHIVE} "${FLANNEL_FILES}"

KUBE_URL=https://github.com/kubernetes/kubernetes/releases/download/${KUBE_VERSION}/kubernetes.tar.gz
KUBE_ARCHIVE=${TEMPORARY_DIRECTORY}/kubernetes.tar.gz
download ${KUBE_URL} ${KUBE_ARCHIVE}
tar -xvzf ${KUBE_ARCHIVE} -C ${TEMPORARY_DIRECTORY}
KUBE_ROOT=${TEMPORARY_DIRECTORY}/kubernetes

export KUBERNETES_SKIP_CONFIRM=Y
export KUBERNETES_DOWNLOAD_TESTS=Y
# Use the upstream utility for downloading the server binaries.
${KUBE_ROOT}/cluster/get-kube-binaries.sh

# TODO figure out how to download different architectures for 1.5 structure.

E2E_DIRECTORY=${KUBE_ROOT}/platforms/${OS}/${ARCH}
E2E_ARCHIVE=${SCRIPT_DIR}/e2e-${KUBE_VERSION}-${ARCH}.tar.gz
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

MASTER_ARCHIVE=${SCRIPT_DIR}/kubernetes-master-${KUBE_VERSION}-${ARCH}.tar.gz
echo "Creating the ${MASTER_ARCHIVE} file."
MASTER_FILES="kube-apiserver kube-controller-manager kubectl kube-dns kube-scheduler"
create_archive ${SERVER_DIRECTORY} ${MASTER_ARCHIVE} "${MASTER_FILES}"

# Copy the loopback binary (needed for CNI) to the server directory.
cp -v ${TEMPORARY_DIRECTORY}/loopback ${SERVER_DIRECTORY}/
WORKER_ARCHIVE=${SCRIPT_DIR}/kubernetes-worker-${KUBE_VERSION}-${ARCH}.tar.gz
echo "Creating the ${WORKER_ARCHIVE} file."
WORKER_FILES="kubectl kubelet kube-proxy loopback"
create_archive ${SERVER_DIRECTORY} ${WORKER_ARCHIVE} "${WORKER_FILES}"

# Change back to the original directory.
cd ${SCRIPT_DIR}
echo "Removing ${TEMPORARY_DIRECTORY}"
rm -rf ${TEMPORARY_DIRECTORY}
echo ""
echo "${0} completed successfully at `date`."
