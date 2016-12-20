#!/usr/bin/env bash
# Build the resources for the flannel charm including CNI and etcdctl binaries.

# The first argument ($1) should be the Flannel version.
# The second argument ($2) should be the CNI verison.
# The third argument ($3) should be the Etcd version.

set -o errexit  # Exit when an individual command fails.
set -o pipefail  # The exit status of the last command is returned.
#set -o xtrace  # Print the commands that are executed.

echo "${0} started at `date`."

FLANNEL_VERSION=${1:-"v0.6.2"}
CNI_VERSION=${2:-"v0.3.0"}
ETCD_VERSION=${3:-"v2.2.5"}

OS=${OS:-"linux"}
ARCH=${ARCH:-"amd64"}

SCRIPT_DIR=${PWD}

# Get the function definition for download.
source ./utilities.sh

# Build the CNI binaries for a version, os and arch.
./build-cni.sh ${CNI_VERSION} ${OS} ${ARCH}

# Build the etcd binaries for a version, os and arch.
./build-etcd.sh ${ETCD_VERSION}

# Remove the existing flannel build directory.
rm -rf build-flannel || true

# Clone the flannel project.
git clone https://github.com/coreos/flannel.git build-flannel

cd build-flannel
# Checkout the desired version.
git checkout -f ${FLANNEL_VERSION}

sed -i 's/-it//' Makefile
sed -i 's/-ti//' Makefile
# Build the flanneld binary in a docker container.
make dist/flanneld-${ARCH}

cd ..

cp -v build-flannel/dist/flanneld-${ARCH} ${TEMPORARY_DIRECTORY}/${OS}/${ARCH}/flanneld

# Create the flannel resource archive name with version os and architecture.
FLANNEL_ARCHIVE=${SCRIPT_DIR}/flannel-resource-${FLANNEL_VERSION}-${OS}-${ARCH}.tar.gz
echo "Creating the ${FLANNEL_ARCHIVE} file."
FLANNEL_FILES="bridge etcdctl flannel flanneld host-local"
create_archive ${TEMPORARY_DIRECTORY}/${OS}/${ARCH} ${FLANNEL_ARCHIVE} "${FLANNEL_FILES}"

cd ${SCRIPT_DIR}
echo "${0} completed successfully at `date`."
