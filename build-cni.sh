#!/usr/bin/env bash
# Build the CNI binaries.

# The first argument ($1) should be the CNI verison.

set -o errexit  # Exit when an individual command fails.
set -o pipefail  # The exit status of the last command is returned.
#set -o xtrace  # Print the commands that are executed.

echo "${0} started at `date`."

CNI_VERSION=${1:-"v0.3.0"}

OS=${OS:-"linux"}
ARCH=${ARCH:-"amd64"}

SCRIPT_DIR=${PWD}

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
  -e "GOARCH=${ARCH}" \
  -v ${PWD}/build-cni:/build-cni \
  golang \
  /bin/bash -c "cd /build-cni && ./build && chown -R ${USER_ID}:${GROUP_ID} /build-cni"

# Copy the binaries to the output directory.
cp -v build-cni/bin/* ${TEMPORARY_DIRECTORY}/${OS}/${ARCH}

cd ${SCRIPT_DIR}
echo "${0} completed successfully at `date`."
