#!/usr/bin/env bash
# Runs the full suite of e2e-runner and gubernator scripts on jenkins.

set -o errexit  # Exit when an individual command fails.
set -o nounset  # Exit when undeclaried variables are used.
set -o pipefail  # The exit status of the last command is returned.
set -o xtrace  # Print the commands that are executed.

# The path to the archive of the JUJU_DATA directory for the specific cloud.
JUJU_DATA_TAR="/var/lib/jenkins/juju/juju_${CLOUD}.tar.gz"
# Uncompress the file that contains the Juju data to the workspace directory.
tar -xvzf ${JUJU_DATA_TAR} -C ${WORKSPACE}

# Set the JUJU_DATA directory for this jenkins workspace.
export JUJU_DATA=${WORKSPACE}/juju

# Deploy a Kubernetes cluster and the e2e charm, and run the test action.
./e2e-runner.sh

# Formats the data and upload to GCE.
./gubernator.sh
