#!/usr/bin/env bash
# Create the resources for the easyrsa charm.

# The first argument ($1) should be the EasyRSA version.

set -o errexit  # Exit when an individual command fails.
set -o pipefail  # The exit status of the last command is returned.
#set -o xtrace  # Print the commands that are executed.

echo "${0} started at `date`."

EASYRSA_VERSION=${1:-"3.0.1"}

SCRIPT_DIR=${PWD}

# Get the function definition for download.
source ./utilities.sh

EASYRSA_URL=https://github.com/OpenVPN/easy-rsa/releases/download/${EASYRSA_VERSION}/EasyRSA-${EASYRSA_VERSION}.tgz
# Copy the easyrsa archive to the script directory because it is not modified.
EASYRSA_ARCHIVE=${SCRIPT_DIR}/easyrsa-resource-${EASYRSA_VERSION}.tgz
echo "Creating the ${EASYRSA_ARCHIVE} file."
download ${EASYRSA_URL} ${EASYRSA_ARCHIVE}

echo "${0} completed successfully at `date`."
