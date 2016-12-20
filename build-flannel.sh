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

SCRIPT_DIR=${PWD}

# Get the function definition for download.
source ./utilities.sh

ARCH=$(get_arch)
OS=$(get_os)

# Grab the user id and group id of this current user.
GROUP_ID=$(id -g)
USER_ID=$(id -u)

# Remove any current build-cni directory.
rm -rf build-cni || true
# Clone the container networking project.
git clone https://github.com/containernetworking/cni.git build-cni
cd build-cni
git checkout -f ${CNI_VERSION}
cd ..

# Build the binaries in a docker container.
docker run \
  --rm \
  -e "GOOS=${OS}" \
  -e "GOARCH=${ARCHITECTURE}" \
  -v ${PWD}/build-cni:/build-cni \
  golang \
  /bin/bash -c "cd /build-cni && ./build && chown -R ${USER_ID}:${GROUP_ID} /build-cni"

# Copy the binaries to the output directory.
cp -v -r build-cni/bin ${TEMPORARY_DIRECTORY}/
# Remove the source build directory.

# Create a url to the Etcd release archive.
ETCD_URL=https://github.com/coreos/etcd/releases/download/${ETCD_VERSION}/etcd-${ETCD_VERSION}-${OS}-${ARCH}.tar.gz
ETCD_ARCHIVE=${TEMPORARY_DIRECTORY}/etcd.tar.gz
download ${ETCD_URL} ${ETCD_ARCHIVE}
tar -xzvf ${ETCD_ARCHIVE} -C ${TEMPORARY_DIRECTORY} etcd-${ETCD_VERSION}-${OS}-${ARCH}/etcdctl
ETCDCTL=${TEMPORARY_DIRECTORY}/etcd-${ETCD_VERSION}-${OS}-${ARCH}/etcdctl
# Copy the etcdctl binary to the temporary directory for the flannel resource.
cp -v ${ETCDCTL} ${TEMPORARY_DIRECTORY}/etcdctl

# Remove any current build-flannel directory.
rm -rf build-flannel || true

# Clone the flannel project.
git clone https://github.com/coreos/flannel.git build-flannel

cd build-flannel
# Checkout the desired version.
git checkout -f ${FLANNEL_VERSION}
# Build the flanneld binary in a docker container.
make dist/flanneld-${ARCHITECTURE}

cd ..

cp -v build-flannel/dist/flanneld-${ARCHITECTURE} ${TEMPORARY_DIRECTORY}/flanneld

# Create the flannel resource archive name with version os and architecture.
FLANNEL_ARCHIVE=${SCRIPT_DIR}/flannel-resource-${FLANNEL_VERSION}-${OS}-${ARCH}.tar.gz
echo "Creating the ${FLANNEL_ARCHIVE} file."
FLANNEL_FILES="bridge etcdctl flannel flanneld host-local"
create_archive ${TEMPORARY_DIRECTORY} ${FLANNEL_ARCHIVE} "${FLANNEL_FILES}"

cd ${SCRIPT_DIR}
echo "${0} completed successfully at `date`."
