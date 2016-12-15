#!/usr/bin/env bash
# Waits for a Kubernetes cluster to be fully deployed and ready to test.

set -o errexit  # Exit when an individual command fails.
set -o pipefail  # The exit status of the last command is returned.
set -o xtrace  # Print the commands that are executed.

echo "${0} started at `date`."

# Define the in-jujubox and juju functions.
source ./define-juju.sh
# Define the utility functions such as run_and_wait.
source ./utilities.sh

# Wait in 10 second increments for the master charm to print running in status.
run_and_wait "juju status kubernetes-master" "Kubernetes master running." 10
# Print out a full juju status.
juju status

# Wait in 10 second increments for "KubeDNS" to show up in cluster-info output.
run_and_wait 'juju run --application kubernetes-master "kubectl cluster-info"' "KubeDNS" 10
# Print out the cluster-info
juju run --application kubernetes-master "kubectl cluster-info"

echo "${0} completed successfully at `date`."
