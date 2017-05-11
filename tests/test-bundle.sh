#!/usr/bin/env bash
# Bundletest cdk

set -o errexit  # Exit when an individual command fails.
set -o pipefail  # The exit status of the last command is returned.
set -o xtrace  # Print the commands that are executed.

echo "Bundle testing started at `date`."

################################################
# Validate params:
################################################

if [ -z "${CLOUD}" ]; then
  echo "Can not test, the cloud is undefined."
  exit 1
fi

if [ -z "${CHANNEL}" ]; then
  echo "Can not test, the channel to get the bundle from is not set."
  exit 1
fi

MATRIX_CMD=""
if [ ${RUN_MATRIX_TESTS} = false ]; then
  echo "Disabling Matrix tests."
  MATRIX_CMD="--no-matrix"
fi


MODEL="big-red-button-${BUILD_NUMBER}"
BUNDLE=`charm show ${BUNDLE_NAME} --channel $CHANNEL id | head -n 2 | tail -n 1 | awk '{print $2}'`

################################################
# Create the model in the right cloud
################################################

# Set the Juju envrionment variables for this jenkins job.
export JUJU_REPOSITORY=${WORKSPACE}/charms

JUJU_CONTROLLER=jenkins-ci-${CLOUD}
juju switch ${JUJU_CONTROLLER}

# Create a model just for this run of the tests.
juju add-model ${MODEL}
# makesure you do not try to delete the model immediately
sleep 10
# Catch all EXITs from this script and make sure to destroy the model.
trap "juju destroy-model -y ${MODEL} || true" EXIT
# Set test mode on the deployment so we dont bloat charm-store deployment count
juju model-config -m ${MODEL} test-mode=1
juju switch ${JUJU_CONTROLLER}:${MODEL}
bundletester ${MATRIX_CMD} -vF -l DEBUG -t ${BUNDLE} -o report.xml -r xml
exit 0
