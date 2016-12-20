#!/usr/bin/env bash
# Build the etcd binaries.

# The first argument ($1) should be the etcd version you would like to build.

set -o errexit  # Exit when an individual command fails.
set -o pipefail  # The exit status of the last command is returned.
#set -o xtrace  # Print the commands that are executed.

echo "${0} started at `date`."

ETCD_VERSION=${1:-"v2.2.5"}

OS=${OS:-"linux"}
ARCH=${ARCH:-"amd64"}

SCRIPT_DIR=${PWD}

# Grab the user id and group id of this current user.
GROUP_ID=$(id -g)
USER_ID=$(id -u)

# Remove any current build-etcd directory.
rm -rf build-etcd || true
# Clone the container networking project.
git clone https://github.com/coreos/etcd.git build-etcd
cd build-etcd
git checkout -f ${ETCD_VERSION}
cd ..

# Build the binaries in a docker container.
docker run \
  --rm \
  -e "GOOS=${OS}" \
  -e "GOARCH=${ARCH}" \
  -v ${PWD}/build-etcd:/build-etcd \
  golang \
  /bin/bash -c "cd /build-etcd &&./build && chown -R ${USER_ID}:${GROUP_ID} /build-etcd"

# Copy the binaries to the output directory.
cp -v build-etcd/bin/* ${TEMPORARY_DIRECTORY}/${OS}/${ARCH}

cd ${SCRIPT_DIR}
echo "${0} completed successfully at `date`."
