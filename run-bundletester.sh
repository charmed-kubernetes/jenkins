#!/usr/bin/env bash
# Runs bundletester against the deployed bundle.

set -o errexit  # Exit when an individual command fails.
set -o pipefail  # The exit status of the last command is returned.
set -o xtrace  # Print the commands that are executed.

echo "${0} started at `date`."

# The first argument is the bundle to test.
BUNDLE=${1:-"kubernetes-core"}
# The second argument is the relative path to the output directory.
OUTPUT_DIRECTORY=${2:-"artifacts/bundletester"}

# Create the output directory.
mkdir -p ${OUTPUT_DIRECTORY}

# Define the juju and charmbox functions.
source ./define-juju.sh

OUTPUT_FILE=${OUTPUT_DIRECTORY}/`date +%s`-results.txt

# When the bundle starts with http it is a url, so download the raw file.
if [[ ${BUNDLE} == "http"* ]]; then
  # Create a relative directory so it is available in Docker under workspace.
  mkdir -p bundle
  BUNDLE_FILE=bundle/bundle.yaml
  # Download the bundle, following redirects (-L) save to specific name.
  curl -L ${BUNDLE} -o ${BUNDLE_FILE}
  # The tests.yaml file configures this bundletester run.
  TESTS_YAML=bundle/tests.yaml
  # Create a tests.yaml file that does not reset the environment.
  cat << EOF > ${TESTS_YAML}
tests: "*"
# Adding tims PPA so we get current dependencies
sources:
  - ppa:tvansteenburgh/ppa
packages:
  - amulet
  - juju-deployer
  - python-jujuclient
reset: false
EOF
  # Create the command to test the downloaded bundle file with the tests.yaml.
  TEST_CMD="bundletester -b workspace/${BUNDLE_FILE} -y workspace/${TEST_YAML} --no-destroy -l DEBUG -v 2>&1 | tee workspace/${OUTPUT_FILE}"
  # Run the test command in charmbox.
  in-charmbox "${TEST_CMD}"
else
  # Download the charm from the Charm Store to the workspace directory.
  CHARM_PULL_CMD="charm pull ${BUNDLE} workspace/${BUNDLE}"
  # The bundle file when downloaded from the 
  BUNDLE_FILE=workspace/${BUNDLE}/bundle.yaml
  TESTS_YAML=workspace/${BUNDLE}/tests/tests.yaml
  # Create the command to test the Charm Store bundle with tests.yaml
  TEST_CMD="bundletester -b ${BUNDLE_FILE} -y ${TESTS_YAML} --no-destroy -l DEBUG -v 2>&1 | tee workspace/${OUTPUT_FILE}"
  # Run the charm pull and test commands in charmbox.
  in-charmbox "${CHARM_PULL_CMD} && ${TEST_CMD}"
fi

echo "${0} completed successfully at `date`."
