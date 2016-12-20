#!/usr/bin/env bash

# Build the CNI binaries from the source in github in a docker container.
# Argument 1 is the version to checkout from the containernetworkking project.
# Argument 2 is the output directory.
# Argument 3 is the desired architecture.
# Argument 4 is the desired os (linux|darwin).

set -o errexit  # Exit when an individual command fails.
set -o pipefail  # The exit status of the last command is returned.
set -o xtrace  # Print the commands that are executed.

CNI_VERSION=${1:-"master"}  # Valid values: v0.3.0
OUTPUT_DIRECTORY=${2:-"cni"}
ARCHITECTURE=${3:-"amd64"}
OS=${4:-"linux"}

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

# Remove the current output directory (if any exists).
rm -rf ${OUTPUT_DIRECTORY} || true
# Copy the binaries to the output directory.
cp -v -r build-cni/bin ${OUTPUT_DIRECTORY}
# Remove the source build directory.
rm -rf build-cni
