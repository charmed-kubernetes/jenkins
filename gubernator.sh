#!/usr/bin/env bash

# This script uploads e2e results from an e2e run using gcloud.

set -o errexit  # Exit when an individual command fails.
set -o nounset  # Exit when undeclaried variables are used.
set -o pipefail  # The exit status of the last command is returned.
set -o xtrace  # Print the commands that are executed.

# Does the logging file exist?
if [ ! -e ./logging.sh ]; then
  # Download the logging script dependency.
  wget https://raw.githubusercontent.com/kubernetes/kubernetes/master/cluster/lib/logging.sh
fi
source logging.sh

# The artifacts directory is where the results are stored.
ARTIFACTS=${ARTIFACTS:-"${PWD}/artifacts"}

# Use a docker container for the gcloud commands.
function gcloud {
  docker run --rm --volumes-from gcloud-config google/cloud-sdk gcloud $@
}
# Use a docker dontainer for the gsutil commands.
function gsutil {
  docker run --rm --volumes-from gcloud-config \
    -v $ARTIFACTS:$ARTIFACTS google/cloud-sdk gsutil $@
}

# Ensure the user has an ACTIVE credentialed account.
if ! gcloud auth list | grep -q "ACTIVE"; then
  echo "Could not find active account when running: \`gcloud auth list\`"
  exit 1
fi

readonly gcs_acl="public-read"
bucket_name="canonical-kubernetes-tests"
echo ""
V=2 kube::log::status "Using bucket ${bucket_name}"

# Check if the bucket exists.
if ! gsutil ls gs:// | grep -q "gs://${bucket_name}/"; then
  V=2 kube::log::status "Creating public bucket ${bucket_name}"
  gsutil mb gs://${bucket_name}/
  # Make all files in the bucket publicly readable
  gsutil acl ch -u AllUsers:R gs://${bucket_name}
else
  V=2 kube::log::status "Bucket already exists"
fi

# The google storage location for e2e-node test results.
GCS_JOBS_PATH=${GCS_JOBS_PATH:-"gs://${bucket_name}/logs/undefined/e2e-node"}
# The local path to the build log file.
BUILD_LOG_PATH="${ARTIFACTS}/build-log.txt"

if [[ ! -e $BUILD_LOG_PATH ]]; then
  echo "Could not find build-log.txt at ${BUILD_LOG_PATH}"
  exit 1
fi

# Get start and end timestamps based on the action_id.log file contents.
start_line=$(grep JUJU_E2E_START ${BUILD_LOG_PATH})
start_time_epoch=$(echo $start_line | cut -d = -f 2)
start_time=$(date -d @${start_time_epoch} '+%m/%d %H:%M:%S.000')
end_line=$(grep JUJU_E2E_END ${BUILD_LOG_PATH})
end_time_epoch=$(echo $end_line | cut -d = -f 2)
end_time=$(date -d @${end_time_epoch} '+%m/%d %H:%M:%S.000')

# Make folder name for build from timestamp
BUILD_STAMP=$(echo $start_time | sed 's/\///' | sed 's/ /_/')

GCS_LOGS_PATH="${GCS_JOBS_PATH}/${BUILD_STAMP}"

# Check if folder for same logs already exists
if gsutil ls "${GCS_JOBS_PATH}" | grep -q "${BUILD_STAMP}"; then
  V=2 kube::log::status "Log files already uploaded"
  echo "Gubernator linked below:"
  echo "k8s-gubernator.appspot.com/build/${GCS_LOGS_PATH}?local=on"
  exit
fi

for result in $(find ${ARTIFACTS} -type d -name "results"); do
  if [[ $result != "" && $result != "${ARTIFACTS}/results" && $result != $ARTIFACTS ]]; then
    mv $result/* $ARTIFACTS
  fi
done

# Upload log files
for upload_attempt in $(seq 3); do
  if [[ -d "${ARTIFACTS}" && -n $(ls -A "${ARTIFACTS}") ]]; then
    V=2 kube::log::status "Uploading artifacts"
    gsutil -m cp -a "${gcs_acl}" -r -c -Z \
      "${ARTIFACTS}" "${GCS_LOGS_PATH}/artifacts" || continue
  fi
  break
done
for upload_attempt in $(seq 3); do
  if [[ -e "${BUILD_LOG_PATH}" ]]; then
    V=2 kube::log::status "Uploading build log"
    gsutil -q cp -Z -a "${gcs_acl}" "${BUILD_LOG_PATH}" "${GCS_LOGS_PATH}" || continue
  fi
  break
done

# Find the k8s version for started.json
version_line=$(grep JUJU_E2E_VERSION ${BUILD_LOG_PATH})
version=$(echo $start_line | cut -d = -f 2)

if [[ -n "${version}" ]]; then
  V=2 kube::log::status "Found Kubernetes version: ${version}"
else
  V=2 kube::log::status "Could not find Kubernetes version"
fi

# Find build result from build-log.txt
if grep -Fxq "Test Suite Passed" "${BUILD_LOG_PATH}"
  then
    build_result="SUCCESS"
else
    build_result="FAILURE"
fi

V=4 kube::log::status "Build result is ${build_result}"

if [[ -e "${ARTIFACTS}/started.json" ]]; then
  rm "${ARTIFACTS}/started.json"
fi

if [[ -e "${ARTIFACTS}/finished.json" ]]; then
  rm "${ARTIFACTS}/finished.json"
fi

V=2 kube::log::status "Constructing started.json and finished.json files"
echo "{" >> "${ARTIFACTS}/started.json"
echo "    \"version\": \"${version}\"," >> "${ARTIFACTS}/started.json"
echo "    \"timestamp\": ${start_time_epoch}," >> "${ARTIFACTS}/started.json"
echo "    \"jenkins-node\": \"${NODE_NAME:-}\"" >> "${ARTIFACTS}/started.json"
echo "}" >> "${ARTIFACTS}/started.json"

echo "{" >> "${ARTIFACTS}/finished.json"
echo "    \"result\": \"${build_result}\"," >> "${ARTIFACTS}/finished.json"
echo "    \"timestamp\": ${end_time_epoch}" >> "${ARTIFACTS}/finished.json"
echo "}" >> "${ARTIFACTS}/finished.json"

# Upload started.json
V=2 kube::log::status "Uploading started.json and finished.json"
V=2 kube::log::status "Run started at ${start_time}"
json_file="${GCS_LOGS_PATH}/started.json"

for upload_attempt in $(seq 3); do
  V=2 kube::log::status "Uploading started.json to ${json_file} (attempt ${upload_attempt})"
  gsutil -q -h "Content-Type:application/json" cp -a "${gcs_acl}" "${ARTIFACTS}/started.json" \
    "${json_file}" || continue
  break
done

# Upload finished.json
for upload_attempt in $(seq 3); do
  V=2 kube::log::status "Uploading finished.json to ${GCS_LOGS_PATH} (attempt ${upload_attempt})"
  gsutil -q -h "Content-Type:application/json" cp -a "${gcs_acl}" "${ARTIFACTS}/finished.json" \
    "${GCS_LOGS_PATH}/finished.json" || continue
  break
done

echo "Gubernator linked below:"
echo "k8s-gubernator.appspot.com/build/${bucket_name}/logs/e2e-node/${BUILD_STAMP}"
