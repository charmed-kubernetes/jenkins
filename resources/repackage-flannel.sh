#!/usr/bin/env bash
# Create the resources for the flannel charm including CNI and etcdctl binaries.

# The first argument ($1) should be the Flannel version.
# The second argument ($2) should be the CNI verison.
# The third argument ($3) should be the Etcd version.

set -o errexit  # Exit when an individual command fails.
set -o pipefail  # The exit status of the last command is returned.
#set -o xtrace  # Print the commands that are executed.

echo "${0} started at `date`."

SCRIPT_DIR=${PWD}

# Get the function definition for download.
source ./utilities.sh
# Get the versions of the software to package.
source resources/versions.sh

ARCH=${ARCH:-"amd64"}
OS=${OS:-"linux"}

# Create a url to the CNI release archive which is linux amd64 right now.
CNI_URL=https://github.com/containernetworking/plugins/releases/download/${CNI_VERSION}/cni-plugins-${ARCH}-${CNI_VERSION}.tgz
CNI_ARCHIVE=${TEMPORARY_DIRECTORY}/linux/${ARCH}/cni-${CNI_VERSION}.tgz
download ${CNI_URL} ${CNI_ARCHIVE}
# NOTE The CNI loopback file is required for the kubernetes-worker resource.
tar -xzvf ${CNI_ARCHIVE} -C ${TEMPORARY_DIRECTORY}/${OS}/${ARCH}

# Create a url to the Etcd release archive.
ETCD_URL=https://github.com/coreos/etcd/releases/download/${ETCD_VERSION}/etcd-${ETCD_VERSION}-${OS}-${ARCH}.tar.gz
ETCD_ARCHIVE=${TEMPORARY_DIRECTORY}/etcd-${ETCD_VERSION}-${OS}-${ARCH}.tar.gz
download ${ETCD_URL} ${ETCD_ARCHIVE}
tar -xzvf ${ETCD_ARCHIVE} -C ${TEMPORARY_DIRECTORY}/ etcd-${ETCD_VERSION}-${OS}-${ARCH}/etcdctl
ETCDCTL=${TEMPORARY_DIRECTORY}/etcd-${ETCD_VERSION}-${OS}-${ARCH}/etcdctl
# Copy the etcdctl binary to the temporary directory for the flannel resource.
cp -v ${ETCDCTL} ${TEMPORARY_DIRECTORY}/${OS}/${ARCH}/etcdctl

# Create a url to the Flannel release archive.
FLANNEL_URL=https://github.com/coreos/flannel/releases/download/${FLANNEL_VERSION}/flannel-${FLANNEL_VERSION}-${OS}-${ARCH}.tar.gz
FLANNEL_TAR_GZ=${TEMPORARY_DIRECTORY}/flannel-${FLANNEL_VERSION}-${OS}-${ARCH}.tar.gz
download ${FLANNEL_URL} ${FLANNEL_TAR_GZ}
tar -xvzf ${FLANNEL_TAR_GZ} -C ${TEMPORARY_DIRECTORY}/${OS}/${ARCH} 

# Create the flannel resource archive name with version os and architecture.
FLANNEL_ARCHIVE=${SCRIPT_DIR}/flannel-resource-${FLANNEL_VERSION}-${OS}-${ARCH}.tar.gz
echo "Creating the ${FLANNEL_ARCHIVE} file."
FLANNEL_FILES="bridge etcdctl flannel flanneld host-local portmap"
create_archive ${TEMPORARY_DIRECTORY}/${OS}/${ARCH} ${FLANNEL_ARCHIVE} "${FLANNEL_FILES}"

cd ${SCRIPT_DIR}
echo "${0} completed successfully at `date`."
