#!/usr/bin/env bash
# Build the etcd binaries.

# The first argument ($1) should be the etcd version you would like to build.

set -o errexit  # Exit when an individual command fails.
set -o pipefail  # The exit status of the last command is returned.
#set -o xtrace  # Print the commands that are executed.

echo "${0} started at `date`."

ETCD_VERSION=${1:-"v2.3.7"}

OS=${OS:-"linux"}
ARCH=${ARCH:-"amd64"}

SCRIPT_DIR=${PWD}

if [ ! -d etcd ]; then
  # Clone the coreos etcd project.
  git clone https://github.com/coreos/etcd.git
fi

cd etcd
# Check out the tag or branch to build.
git checkout -f ${ETCD_VERSION}
cd ..

# Grab the user id and group id of this current user.
GROUP_ID=$(id -g)
USER_ID=$(id -u)

echo "Building etcd for ${OS} and ${ARCH} in a docker conatiner..."
docker run \
  --rm \
  -e "GOOS=${OS}" \
  -e "GOARCH=${ARCH}" \
  -v ${PWD}/etcd:/etcd \
  golang \
  /bin/bash -c "cd /etcd &&./build && chown -R ${USER_ID}:${GROUP_ID} /etcd"

# Copy the binaries to the output directory.
cp -v etcd/bin/* ${TEMPORARY_DIRECTORY}/${OS}/${ARCH}

cd ${SCRIPT_DIR}
echo "${0} completed successfully at `date`."
