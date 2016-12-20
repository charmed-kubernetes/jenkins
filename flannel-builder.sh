#!/usr/bin/env bash

# Build the flannel binary from the source in github in a docker container.
# Argument 1 is the version to checkout from the coreos project.
# Argument 2 is the output directory.
# Argument 3 is the desired architecture.

set -o errexit  # Exit when an individual command fails.
set -o pipefail  # The exit status of the last command is returned.
set -o xtrace  # Print the commands that are executed.

FLANNEL_VERSION=${1:-"master"}  # Valid values: v0.6.1 | v0.6.2
OUTPUT_DIRECTORY=${2:-"flannel"}
ARCHITECTURE=${3:-"amd64"}

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

cp -v build-flannel/dist/flanneld-${ARCHITECTURE} ${OUTPUT_DIRECTORY}/flanneld
# Remove the source directory.
rm -rf build-flannel
