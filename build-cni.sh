#!/usr/bin/env bash
# Build the CNI binaries.

# The first argument ($1) should be the CNI verison you would like to build.

set -o errexit  # Exit when an individual command fails.
set -o pipefail  # The exit status of the last command is returned.
#set -o xtrace  # Print the commands that are executed.

echo "${0} started at `date`."

CNI_VERSION=${CNI_VERSION:-"v0.5.1"}

OS=${OS:-"linux"}
ARCH=${ARCH:-"amd64"}

SCRIPT_DIR=${PWD}

if [ ! -d cni ]; then
  # Clone the containernetworking cni project.
  git clone https://github.com/containernetworking/cni.git cni
fi

cd cni
# Check out the tag or branch to build.
git checkout -f ${CNI_VERSION}
cd ..

# Grab the user id and group id of this current user.
GROUP_ID=$(id -g)
USER_ID=$(id -u)

echo "Building cni for ${OS} and ${ARCH} in a docker container..."
docker run \
  --rm \
  -e "GOOS=${OS}" \
  -e "GOARCH=${ARCH}" \
  -v ${PWD}/cni:/cni \
  golang \
  /bin/bash -c "cd /cni && ./build && chown -R ${USER_ID}:${GROUP_ID} /cni"

# Copy the binaries to the output directory.
cp -v cni/bin/* ${TEMPORARY_DIRECTORY}/${OS}/${ARCH}

source ${SCRIPT_DIR}/utilities.sh
# Create the cni resource archive for kubernetes-worker charm.
create_archive cni/bin ${SCRIPT_DIR}/cni-${ARCH}-${VERSION}.tgz '*'

cd ${SCRIPT_DIR}
echo "${0} completed successfully at `date`."
