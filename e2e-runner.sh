#!/usr/bin/env bash
# Deploys a kubernetes bundle, and an e2e charm and runs the e2e tests.

source ./common.sh

set -o errexit  # Exit when an individual command fails.
set -o nounset  # Exit when undeclaried variables are used.
set -o pipefail  # The exit status of the last command is returned.
set -o xtrace  # Print the commands that are executed.

# Create a model namme for this build.
MODEL="jenkins-e2e-${BUILD_ID}"
# Create a model just for this run of the tests.
in-jujubox "sudo chown -R ubuntu:ubuntu /home/ubuntu/.local/share/juju && juju add-model $MODEL"
# Catch all EXITs from this script and make sure to destroy the model.
trap "juju destroy-model -y $MODEL" EXIT

# Set test mode on the deployment so we dont bloat charm-store deployment count
juju model-config test-mode=1

# Deploy the kubernetes bundle.
juju deploy cs:~containers/kubernetes-core
# Deploy the e2e charm.
juju deploy cs:~containers/kubernetes-e2e
juju add-unit kubernetes-worker
juju relate kubernetes-e2e kubernetes-master
juju relate kubernetes-e2e easyrsa

# Wait for the deployment to be ready.
set +x
until juju status | grep "Ready to test."; do
  juju status
  sleep 10
done
until [ "$(juju status | grep "Kubernetes worker running." | wc -l)" -eq "2" ]; do
  juju status
  sleep 10
done

# Run the test action.
ACTION_ID=$(juju run-action kubernetes-e2e/0 test | cut -d " " -f 5)
# Wait for the action to be complete
while juju show-action-status $ACTION_ID | grep pending || juju show-action-status $ACTION_ID | grep running; do
  sleep 1
done
juju show-action-status $ACTION_ID

# Download results and move them to the bind mount
set -x
in-jujubox "juju scp kubernetes-e2e/0:${ACTION_ID}.log.tar.gz /tmp/e2e.log.tar.gz; sudo mv /tmp/e2e.log.tar.gz ./workspace"
in-jujubox "juju scp kubernetes-e2e/0:${ACTION_ID}-junit.tar.gz /tmp/e2e-junit.tar.gz; sudo mv /tmp/e2e-junit.tar.gz ./workspace"

# Remove the gcloud-config container.
docker rm gcloud-config
# Search for the container by name.
CONFIG_CONTAINER=$(docker ps -aq -f name=gcloud-config)
echo $CONFIG_CONTAINER

# This script assumes there is a gce.json file in $GCE_ACCOUNT_CREDENTIAL.
# Keep this service account credential (.p12) file in a Jenkins Secret
if [ -z $CONFIG_CONTAINER ]; then
  docker run \
    -v $GCE_ACCOUNT_CREDENTIAL:/root/gce.json \
    --name gcloud-config \
    google/cloud-sdk \
    gcloud auth activate-service-account \
    --key-file /root/gce.json \
    --project ubuntu-benchmarking
fi

ARTIFACTS=$PWD/artifacts

# Extract the results into the artifacts directory.
mkdir -p $ARTIFACTS
tar xvfz $WORKSPACE/e2e-junit.tar.gz -C $ARTIFACTS
tar xvfz $WORKSPACE/e2e.log.tar.gz -C $ARTIFACTS

# Rename the ACTION_ID log file to build-log.txt
mv $ARTIFACTS/${ACTION_ID}.log $ARTIFACTS/build-log.txt
# Call the gubernator script with some environment variables defined.
GCS_JOBS_PATH=gs://canonical-kubernetes-tests/logs/gce-e2e-node ARTIFACTS=$PWD/artifacts ./gubernator.sh
