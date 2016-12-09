#!/usr/bin/env bash
# Builds the kubernetes project to create the output needed for the Juju Charms.

set -o errexit  # Exit when an individual command fails.
set -o pipefail  # The exit status of the last command is returned.
set -o xtrace  # Print the commands that are executed.

echo "${0} started at `date`."

SCRIPT_DIR=${PWD}

source ./util.sh

OS=$(get_os)

# The version is the first argument.
VERSION=${1:-"v1.5.0"}
# The URL is the second argument.
KUBERNETES_GIT_URL=${2:-"https://github.com/kubernetes/kubernetes.git"}

KUBE_ROOT=./

git clone ${KUBERNETES_GIT_URL} ${KUBE_ROOT}
git checkout -f ${VERSION}

echo "Starting build `date`."

build-tools/run.sh make all
# WARNING: Build all only builds for the current architecture.
# build-tools/run.sh make all \
#   WHAT='cmd/kube-apiserver \
#     cmd/kube-controller-manager \
#     cmd/kube-dns \
#     cmd/kube-proxy \
#     cmd/kubectl \
#     cmd/kubelet \
#     plugin/cmd/kube-scheduler'
# 
# echo "Build finished `date`"
# 
# OUTPUT_DIRECTORY=./_output/dockerized/bin/${OS}/${ARCH}
# 
# MASTER_ARCHIVE=${SCRIPT_DIR}/kubernetes-master-${VERSION}-${ARCH}.tar.gz
# echo "Creating the ${MASTER_ARCHIVE} file."
# MASTER_FILES="kube-apiserver kube-controller-manager kubectl kube-dns kube-scheduler"
# create_archive ${SERVER_DIRECTORY} ${MASTER_ARCHIVE} "${MASTER_FILES}"
# 
# WORKER_ARCHIVE=${SCRIPT_DIR}/kubernetes-worker-${VERSION}-${ARCH}.tar.gz
# echo "Creating the ${WORKER_ARCHIVE} file."
# WORKER_FILES="kubectl kubelet kube-proxy"
# create_archive ${SERVER_DIRECTORY} ${WORKER_ARCHIVE} "${WORKER_FILES}"

# Change back to the original directory.
cd ${SCRIPT_DIR}
echo ""
echo "${0} completed successfully at `date`."
