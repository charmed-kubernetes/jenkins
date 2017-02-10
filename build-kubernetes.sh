#!/usr/bin/env bash
# Create the resources for the Canonical Distribution of Kubernetes.

# The first argument ($1) should be the Kubernetes version.

# NOTE The kubernetes-worker resource depends on a CNI resource loopback which
# is created in the repackage-flannel.sh script.

set -o errexit  # Exit when an individual command fails.
set -o pipefail  # The exit status of the last command is returned.
#set -o xtrace  # Print the commands that are executed.

echo "${0} started at `date`."

KUBE_VERSION=${KUBE_VERSION:-"v1.5.2"}

SCRIPT_DIR=${PWD}

# Get the create_archive function definition.
source ./utilities.sh

KUBE_ROOT=${SCRIPT_DIR}/kubernetes

if [ ! -d ${KUBE_ROOT} ]; then
  git clone https://github.com/kubernetes/kubernetes.git ${KUBE_ROOT}
fi

cd ${KUBE_ROOT}
# Checkout a specific branch or tag version of Kubernetes.
git checkout -f ${KUBE_VERSION}

# The build directory changed between 1.4 to 1.5
if [ -d build-tools ]; then
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
TARGETS='cmd/kube-proxy \
  cmd/kube-apiserver \
  cmd/kube-controller-manager \
  cmd/kubelet \
  plugin/cmd/kube-scheduler \
  cmd/kubectl \
  test/e2e/e2e.test \
  vendor/github.com/onsi/ginkgo/ginkgo \
  test/e2e_node/e2e_node.test'
echo "${BUILD_DIR}/run.sh make cross WHAT="${TARGETS}""
# Only build the targets we actually use.
${BUILD_DIR}/run.sh make cross WHAT="${TARGETS}"

echo "Build finished `date`"

OS=${OS:-"linux"}
ARCHITECTURES=${ARCHITECTURES:-"amd64"}

# Iterate over the supported architectures.
for ARCH in ${ARCHITECTURES}; do
  OUTPUT_DIRECTORY=${KUBE_ROOT}/_output/dockerized/bin/${OS}/${ARCH}
  # Check if the architecture specific directory exists.
  if [ -d ${OUTPUT_DIRECTORY} ]; then
    E2E_ARCHIVE=${SCRIPT_DIR}/e2e-${KUBE_VERSION}-${ARCH}.tar.gz
    echo "Creating the ${E2E_ARCHIVE} file."
    E2E_FILES="kubectl ginkgo e2e.test e2e_node.test"
    if [ -e ${OUTPUT_DIRECTORY}/e2e.test ]; then
      create_archive ${OUTPUT_DIRECTORY} ${E2E_ARCHIVE} "${E2E_FILES}"
    else
        echo "The ${ARCH}/e2e.test file does not exist."
        echo "Can not create the e2e-${KUBE_VERSION}-${ARCH}.tar.gz archive."
    fi

    MASTER_ARCHIVE=${SCRIPT_DIR}/kubernetes-master-${KUBE_VERSION}-${ARCH}.tar.gz
    echo "Creating the ${MASTER_ARCHIVE} file."
    MASTER_FILES="kube-apiserver kube-controller-manager kubectl kube-scheduler"
    create_archive ${OUTPUT_DIRECTORY} ${MASTER_ARCHIVE} "${MASTER_FILES}"

    # This loopback file is created in the build-cni.sh script.
    CNI_LOOPBACK=${TEMPORARY_DIRECTORY}/${OS}/${ARCH}/loopback
    if [ -e ${CNI_LOOPBACK} ]; then
      # Copy the CNI loopback plugin to the output directory for archival.
      cp -v ${CNI_LOOPBACK} ${OUTPUT_DIRECTORY}
      WORKER_ARCHIVE=${SCRIPT_DIR}/kubernetes-worker-${KUBE_VERSION}-${ARCH}.tar.gz
      echo "Creating the ${WORKER_ARCHIVE} file."
      WORKER_FILES="kubectl kubelet kube-proxy loopback"
      create_archive ${OUTPUT_DIRECTORY} ${WORKER_ARCHIVE} "${WORKER_FILES}"
    else
      echo "The ${CNI_LOOPBACK} is missing for ${ARCH} can not create resource."
    fi
  else
    echo "Missing architecture: ${ARCH}"
  fi
done
# Change back to the original directory.
cd ${SCRIPT_DIR}
echo ""
echo "${0} completed successfully at `date`."
