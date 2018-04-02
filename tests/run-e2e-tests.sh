#!/usr/bin/env bash
# Run the test action on the kubernetes-e2e charm.

set -o errexit  # Exit when an individual command fails.
set -o pipefail  # The exit status of the last command is returned.
set -o xtrace  # Print the commands that are executed.

echo "${0} started at `date`."

# First argument is the controller name for this build.
CONTROLLER=${1:-"controller-is-undefined"}
# Second argument is the model name for this build.
MODEL=${2:-"model-is-undefined"}
# Third argument is the output directory.
OUTPUT_DIRECTORY=${3:-"artifacts"}

# Create the output directory.
mkdir -p ${OUTPUT_DIRECTORY}

# Run the e2e test action.
ACTION_ID=$(juju run-action -m ${CONTROLLER}:${MODEL} kubernetes-e2e/0 test | cut -d " " -f 5)
# Show the action results (wait up to 2 hours for the action to finish)
outcome=$(juju show-action-output -m ${CONTROLLER}:${MODEL} --wait=2h ${ACTION_ID})
echo ${outcome}

# Download results from the charm and move them to the the volume directory.
juju scp -m ${CONTROLLER}:${MODEL} kubernetes-e2e/0:${ACTION_ID}.log.tar.gz \
  e2e.log.tar.gz
juju scp -m ${CONTROLLER}:${MODEL} kubernetes-e2e/0:${ACTION_ID}-junit.tar.gz \
  e2e-junit.tar.gz

if [[ "$outcome" == *"failed"* ]]
then
  echo "${0} failed at `date`."
  mkdir -p ${OUTPUT_DIRECTORY}/failed
  tar -xvzf e2e.log.tar.gz -C ${OUTPUT_DIRECTORY}/failed
  tail -n 30 ${OUTPUT_DIRECTORY}/failed/${ACTION_ID}.log
  rm -rf ${OUTPUT_DIRECTORY}/failed
  exit 1
fi

# Extract the results into the output directory.
tar -xvzf e2e-junit.tar.gz -C ${OUTPUT_DIRECTORY}
tar -xvzf e2e.log.tar.gz -C ${OUTPUT_DIRECTORY}

# Print the tail of the action output to show our success or failure.
tail -n 30 ${OUTPUT_DIRECTORY}/${ACTION_ID}.log
# Rename the ACTION_ID log file to build-log.txt
mv ${OUTPUT_DIRECTORY}/${ACTION_ID}.log ${OUTPUT_DIRECTORY}/build-log.txt

echo "${0} completed successfully at `date`."
