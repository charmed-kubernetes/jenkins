#!/usr/bin/env bash
# Builds the kubernetes project to create the output needed for the Juju Charms.

set -o errexit  # Exit when an individual command fails.
set -o pipefail  # The exit status of the last command is returned.
#set -o xtrace  # Print the commands that are executed.

echo "${0} started at `date`."

SCRIPT_DIR=${PWD}

source ./util.sh

# The version is the first optional argument.
VERSION=${1:-"v1.5.0"}
# The URL is the second optional argument.
KUBERNETES_GIT_URL=${2:-"https://github.com/kubernetes/kubernetes.git"}

KUBE_ROOT=${SCRIPT_DIR}/kubernetes

git clone ${KUBERNETES_GIT_URL} ${KUBE_ROOT}
cd ${KUBE_ROOT}
git checkout -f ${VERSION}

# The build directory changed between 1.4 to 1.5
if [[ -d build-tools ]]; then
  BUILD_DIR=build-tools
else
  BUILD_DIR=build
fi

echo "Starting build `date`."

# Possible targets from build-tools/run.sh make all
# cmd/kube-dns
# cmd/kube-proxy
# cmd/kube-apiserver
# cmd/kube-controller-manager
# cmd/kubelet
# cmd/kubeadm
# cmd/hyperkube
# cmd/kube-discovery
# plugin/cmd/kube-scheduler
# cmd/kubectl
# federation/cmd/kubefed
# cmd/gendocs
# cmd/genkubedocs
# cmd/genman
# cmd/genyaml
# cmd/mungedocs
# cmd/genswaggertypedocs
# cmd/linkcheck
# examples/k8petstore/web-server/src
# federation/cmd/genfeddocs
# vendor/github.com/onsi/ginkgo/ginkgo
# test/e2e/e2e.test
# cmd/kubemark
# vendor/github.com/onsi/ginkgo/ginkgo
# test/e2e_node/e2e_node.test

# Create a list of the targets we are interested in.
TARGETS='cmd/kube-dns \
  cmd/kube-proxy \
  cmd/kube-apiserver \
  cmd/kube-controller-manager \
  cmd/kubelet \
  plugin/cmd/kube-scheduler \
  cmd/kubectl \
  test/e2e/e2e.test \
  vendor/github.com/onsi/ginkgo/ginkgo \
  test/e2e_node/e2e_node.test'
# Only build the targets we are interested in.
${BUILD_DIR}/run.sh make all WHAT="${TARGETS}"

echo "Build finished `date`"

OS=$(get_os)
ARCHITECTURES="amd64 arm64 ppc64le s390x"
# Iterate over the supported architectures.
for ARCH in ${ARCHITECTURES}; do
  OUTPUT_DIRECTORY=${KUBE_ROOT}/_output/dockerized/bin/${OS}/${ARCH}
  # Check if the architecture specific directory exists.
  if [ -d ${OUTPUT_DIRECTORY} ]; then
    E2E_ARCHIVE=${SCRIPT_DIR}/e2e-${VERSION}-${ARCH}.tar.gz
    echo "Creating the ${E2E_ARCHIVE} file."
    E2E_FILES="kubectl ginkgo e2e.test e2e_node.test"
    create_archive ${OUTPUT_DIRECTORY} ${E2E_ARCHIVE} "${E2E_FILES}"

    MASTER_ARCHIVE=${SCRIPT_DIR}/kubernetes-master-${VERSION}-${ARCH}.tar.gz
    echo "Creating the ${MASTER_ARCHIVE} file."
    MASTER_FILES="kube-apiserver kube-controller-manager kubectl kube-dns kube-scheduler"
    create_archive ${OUTPUT_DIRECTORY} ${MASTER_ARCHIVE} "${MASTER_FILES}"

    WORKER_ARCHIVE=${SCRIPT_DIR}/kubernetes-worker-${VERSION}-${ARCH}.tar.gz
    echo "Creating the ${WORKER_ARCHIVE} file."
    WORKER_FILES="kubectl kubelet kube-proxy"
    create_archive ${OUTPUT_DIRECTORY} ${WORKER_ARCHIVE} "${WORKER_FILES}"
  else
    echo "Missing architecture: ${ARCH}"
  fi
done

# Change back to the original directory.
cd ${SCRIPT_DIR}
echo ""
echo "${0} completed successfully at `date`."
