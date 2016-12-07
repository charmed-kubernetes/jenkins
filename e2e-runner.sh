#!/usr/bin/env bash
# Deploys a kubernetes bundle, and an e2e charm and runs the e2e tests.

set -o errexit  # Exit when an individual command fails.
set -o nounset  # Exit when undeclaried variables are used.
set -o pipefail  # The exit status of the last command is returned.
set -o xtrace  # Print the commands that are executed.

# The maximum amount of seconds to wait for a complete deployment.
MAXIMUM_WAIT_SECONDS=3600

# The check_time function requires two parameters start_time and max_seconds.
function check_time () {
  local start_time=$1
  local maximum_seconds=$2
  local current_time=`date +"%s"`
  local difference=$(expr ${current_time} - ${start_time})
  # When the difference is greater than maximum seconds, exit this script.
  if [ ${difference} -gt ${maximum_seconds} ]; then
    echo "The process is taking more than ${maximum_seconds} seconds!"
    # End this script because too much time has passed.
    exit 3
  fi
}

# A function to run a command in the jujubox container.
function in-jujubox {
  { set +x; } 2> /dev/null
  local command=$@
  # Format the command to run inside the container.
  docker run \
    --rm \
    -v ${JUJU_DATA}:/home/ubuntu/.local/share/juju \
    -v ${WORKSPACE}:/home/ubuntu/workspace \
    --entrypoint /bin/bash \
    jujusolutions/jujubox:latest \
    -c "${command}"
  { set -x; } 2> /dev/null
}

# A function to make juju commands run inside a container.
function juju {
  { set +x; } 2> /dev/null
  local args=$@
  # Call the function that runs the commands in a jujubox container.
  in-jujubox juju ${args}
  { set -x; } 2> /dev/null
}

# Create a model namme for this build.
MODEL="${BUILD_TAG}"
# Create a model just for this run of the tests.
in-jujubox "sudo chown -R ubuntu:ubuntu /home/ubuntu/.local/share/juju && juju add-model ${MODEL}"
# Catch all EXITs from this script and make sure to destroy the model.
trap "juju destroy-model -y ${MODEL}" EXIT

# Set test mode on the deployment so we dont bloat charm-store deployment count
juju model-config -m ${MODEL} test-mode=1

# Deploy the kubernetes bundle.
juju deploy cs:~containers/kubernetes-core
# Deploy the e2e charm.
juju deploy cs:~containers/kubernetes-e2e
juju add-unit kubernetes-worker
juju relate kubernetes-e2e kubernetes-master
juju relate kubernetes-e2e easyrsa

START_TIME=`date +"%s"`
{ set +x; } 2>/dev/null
# Wait for the kubernetes-e2e charm emit the "Ready to test." status.
until juju status -m ${MODEL} kubernetes-e2e | grep "Ready to test."; do
  check_time ${START_TIME} ${MAXIMUM_WAIT_SECONDS}
  sleep 10
done
# Wait for the kubernetes-worker charms to emit the "worker running" status.
until [ "$(juju status -m ${MODEL} kubernetes-worker | grep "Kubernetes worker running." | wc -l)" -eq "2" ]; do
  check_time ${START_TIME} ${MAXIMUM_WAIT_SECONDS}
  sleep 10
done
{ set -x; } 2>/dev/null
# Print out the full status one time.
juju status -m ${MODEL}

# Run the e2e test action.
ACTION_ID=$(juju run-action kubernetes-e2e/0 test | cut -d " " -f 5)

START_TIME=`date +"%s"`
{ set +x; } 2>/dev/null
# Wait for the action to be complete.
while juju show-action-status ${ACTION_ID} | grep pending || juju show-action-status ${ACTION_ID} | grep running; do
  check_time ${START_TIME} ${MAXIMUM_WAIT_SECONDS}
  sleep 5
done
{ set -x; } 2>/dev/null
# Print out the action result.
juju show-action-status ${ACTION_ID}

# Download results and move them to the bind mount
in-jujubox "juju scp kubernetes-e2e/0:${ACTION_ID}.log.tar.gz /tmp/e2e.log.tar.gz; sudo mv /tmp/e2e.log.tar.gz /home/ubuntu/workspace"
in-jujubox "juju scp kubernetes-e2e/0:${ACTION_ID}-junit.tar.gz /tmp/e2e-junit.tar.gz; sudo mv /tmp/e2e-junit.tar.gz /home/ubuntu/workspace"

export ARTIFACTS=${WORKSPACE}/artifacts
# Create the artifacts directory.
mkdir -p ${ARTIFACTS}
# Extract the results into the artifacts directory.
tar xvfz ${WORKSPACE}/e2e-junit.tar.gz -C ${ARTIFACTS}
tar xvfz ${WORKSPACE}/e2e.log.tar.gz -C ${ARTIFACTS}
# Rename the ACTION_ID log file to build-log.txt
mv ${ARTIFACTS}/${ACTION_ID}.log ${ARTIFACTS}/build-log.txt
