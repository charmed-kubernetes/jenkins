#!/bin/bash

set -o errexit  # Exit when an individual command fails.
set -o nounset  # Exit when undeclaried variables are used.
set -o pipefail  # The exit status of the last command is returned.
set -o xtrace  # Print the commands that are executed.


# Configure juju
JUJU_CONTROLLER="jenkins-ci-${CLOUD}"
juju switch ${JUJU_CONTROLLER}
MODEL="test-combination-${BUILD_NUMBER}"
juju add-model ${MODEL}
sleep 10
trap "juju destroy-model -y ${MODEL} || true" EXIT
juju model-config -m ${MODEL} test-mode=1
juju switch ${MODEL}


# Ge the bundle localy
BUNDLE_NAME_AND_REVISION="cs:~containers/bundle/"${BUNDLE_NAME}"-"${REVISION}
charm pull ${BUNDLE_NAME_AND_REVISION}
if [ ! ${SNAP_CHANNEL} = "" ]; then
  ./tests/set-snap-channel.py ${BUNDLE_NAME} ${SNAP_CHANNEL}
fi

# Deploy bundle
BUNDLE=${BUNDLE_NAME}/bundle.yaml
# Deploy the kubernetes bundle.
juju deploy ${BUNDLE}
juju add-unit kubernetes-worker
juju deploy cs:~containers/kubernetes-e2e
juju relate kubernetes-e2e kubernetes-master
juju relate kubernetes-e2e easyrsa
juju config kubernetes-master allow-privileged=true
juju config kubernetes-worker allow-privileged=true
sleep 20


# Wait for deployment to finish
source ./utilities.sh
run_and_wait "juju status kubernetes-e2e" "Ready to test." 10
run_and_wait "juju status kubernetes-master" "Kubernetes master running." 10
juju status
run_and_wait 'juju run --application kubernetes-master /snap/bin/kubectl cluster-info' "KubeDNS" 10
juju run --application kubernetes-master /snap/bin/kubectl cluster-info


# Run e2e tests
OUTPUT_DIRECTORY=${WORKSPACE}/artifacts
mkdir -p ${OUTPUT_DIRECTORY}
ACTION_ID=$(juju run-action kubernetes-e2e/0 test | cut -d " " -f 5)
# Wait 2 hour for the action to complete.
juju show-action-output --wait=2h ${ACTION_ID}
juju show-action-output ${ACTION_ID}

# Download results from the charm and move them to the the volume directory.
juju scp kubernetes-e2e/0:${ACTION_ID}.log.tar.gz e2e.log.tar.gz
juju scp kubernetes-e2e/0:${ACTION_ID}-junit.tar.gz e2e-junit.tar.gz

# Extract the results into the output directory.
tar -xvzf e2e-junit.tar.gz -C ${OUTPUT_DIRECTORY}
tar -xvzf e2e.log.tar.gz -C ${OUTPUT_DIRECTORY}

# Print the tail of the action output to show our success or failure.
tail -n 30 ${OUTPUT_DIRECTORY}/${ACTION_ID}.log
# Rename the ACTION_ID log file to build-log.txt
mv ${OUTPUT_DIRECTORY}/${ACTION_ID}.log ${OUTPUT_DIRECTORY}/build-log.txt

echo "${0} completed successfully at `date`."
