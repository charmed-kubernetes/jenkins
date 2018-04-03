#!/usr/bin/env bash
# Waits for a Kubernetes cluster to be fully deployed and ready to test.

set -o errexit  # Exit when an individual command fails.
set -o pipefail  # The exit status of the last command is returned.
set -o xtrace  # Print the commands that are executed.

echo "${0} started at `date`."

# Define the utility functions such as run_and_wait.
source ./utilities.sh

# First argument is the controller name for this build.
CONTROLLER=${1:-"controller-is-undefined"}
# Second argument is the model name for this build.
MODEL=${2:-"model-is-undefined"}

# Wait in 10 second increments for the master charm to print running in status.
run_and_wait \
  "juju status -m ${CONTROLLER}:${MODEL} kubernetes-master" \
  "Kubernetes master running." \
  10

# Master is running; ensure the rest of the deployment is ready (nothing in
# blocked, maintenance, error, etc).
wait_for_ready \
  "juju status -m ${CONTROLLER}:${MODEL}"

# Print out a full juju status.
juju status -m ${CONTROLLER}:${MODEL}

# Wait in 10 second increments for "KubeDNS" to show up in cluster-info output.
run_and_wait \
  "juju run -m ${CONTROLLER}:${MODEL} --application kubernetes-master /snap/bin/kubectl cluster-info" \
  "KubeDNS" \
  10

# Print out the cluster-info
juju run -m ${CONTROLLER}:${MODEL} --application kubernetes-master \
  "/snap/bin/kubectl cluster-info"

echo "${0} completed successfully at `date`."
