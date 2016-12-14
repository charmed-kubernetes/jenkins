#!/usr/bin/env bash

# This script uploads e2e results from an e2e run using gcloud.

set -o errexit  # Exit when an individual command fails.
set -o nounset  # Exit when undeclaried variables are used.
set -o pipefail  # The exit status of the last command is returned.
set -o xtrace  # Print the commands that are executed.

echo "${0} started at `date`."

# The location of the artifacts from the e2e run that are to be uploaded.
export ARTIFACTS=${1:-"artifacts"}

# Use a docker container for the gcloud commands.
function gcloud {
  docker run \
    --rm \
    --volumes-from gcloud-config \
    google/cloud-sdk \
    gcloud "$@"
}

# Use a docker container for the gsutil commands.
function gsutil {
  docker run \
    --rm \
    --volumes-from gcloud-config \
    -v ${ARTIFACTS}:${ARTIFACTS} \
    google/cloud-sdk \
    gsutil $@
}

LOG_LEVEL=${LOG_LEVEL:-1}

# Put a timestamp on the message if log level is greater than zero.
function log () {
  if [[ ${LOG_LEVEL} -gt 0 ]]; then
    current_time=$(date +"[%m%d %H:%M:%S]")
    echo "${current_time} ${1}"
  fi
}

# Remove any old gcloud-config containers.
docker rm gcloud-config || true
# Are there any gcloud-config containers left?
CONFIG_CONTAINER=$(docker ps -a -q -f name=gcloud-config)

if [ -z ${CONFIG_CONTAINER} ]; then
  # Authorize the service account and save the container as "glcoud-config".
  docker run \
    -v ${GCE_ACCOUNT_CREDENTIAL}:/root/gce.json \
    --name gcloud-config \
    google/cloud-sdk \
    gcloud auth activate-service-account \
    --key-file /root/gce.json \
    --project ubuntu-benchmarking
fi

# Ensure the user has an ACTIVE credentialed account.
if ! gcloud auth list | grep -q "ACTIVE"; then
  echo "Could not find active account when running: \`gcloud auth list\`"
  exit 1
fi

readonly gcs_acl="public-read"

BUCKET_NAME="canonical-kubernetes-tests"
log "Using bucket ${BUCKET_NAME}"

# Check if the bucket exists.
if ! gsutil ls gs:// | grep -q "gs://${BUCKET_NAME}/"; then
  log "Creating public bucket ${BUCKET_NAME}"
  gsutil mb gs://${BUCKET_NAME}/
  # Make all files in the bucket publicly readable
  gsutil acl ch -u AllUsers:R gs://${BUCKET_NAME}
else
  log "Bucket already exists"
fi

# The name must start with kubernetes to be picked up by filter.
GCS_JOB_NAME=kubernetes-${CLOUD}-e2e-node
# The google storage location for e2e-node test results.
GCS_JOBS_PATH=${GCS_JOBS_PATH:-"gs://${BUCKET_NAME}/logs/${GCS_JOB_NAME}"}
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

# Create a folder safe name for build timestamp
BUILD_STAMP=$(date -d @${start_time_epoch} '+%m%d%H%M%S000')

GCS_LOGS_PATH="${GCS_JOBS_PATH}/${BUILD_STAMP}"

# Check if folder for same logs already exists
if gsutil ls "${GCS_JOBS_PATH}" | grep -q "${BUILD_STAMP}"; then
  log "Log files already uploaded"
  echo "Gubernator linked below:"
  echo "https://k8s-gubernator.appspot.com/build/${BUCKET_NAME}/logs/${GCS_JOB_NAME}/${BUILD_STAMP}"
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
    log "Uploading artifacts"
    gsutil -m cp -a "${gcs_acl}" -r -c -Z \
      "${ARTIFACTS}" "${GCS_LOGS_PATH}/artifacts" || continue
  fi
  break
done
for upload_attempt in $(seq 3); do
  if [[ -e "${BUILD_LOG_PATH}" ]]; then
    log "Uploading build log"
    gsutil -q cp -Z -a "${gcs_acl}" "${BUILD_LOG_PATH}" "${GCS_LOGS_PATH}" || continue
  fi
  break
done

# Find the k8s version for started.json
version_line=$(grep JUJU_E2E_VERSION ${BUILD_LOG_PATH})
version=$(echo $start_line | cut -d = -f 2)

if [[ -n "${version}" ]]; then
  log "Found Kubernetes version: ${version}"
else
  log "Could not find Kubernetes version"
fi

# Find build result from build-log.txt
if grep -Fxq "Test Suite Passed" "${BUILD_LOG_PATH}"
  then
    build_result="SUCCESS"
else
    build_result="FAILURE"
fi

log "Build result is ${build_result}"

if [[ -e "${ARTIFACTS}/started.json" ]]; then
  rm "${ARTIFACTS}/started.json"
fi

if [[ -e "${ARTIFACTS}/finished.json" ]]; then
  rm "${ARTIFACTS}/finished.json"
fi

log "Constructing started.json and finished.json files"
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
log "Uploading started.json and finished.json"
log "Run started at ${start_time}"
json_file="${GCS_LOGS_PATH}/started.json"

for upload_attempt in $(seq 3); do
  log "Uploading started.json to ${json_file} (attempt ${upload_attempt})"
  gsutil -q -h "Content-Type:application/json" cp -a "${gcs_acl}" "${ARTIFACTS}/started.json" \
    "${json_file}" || continue
  break
done

# Upload finished.json
for upload_attempt in $(seq 3); do
  log "Uploading finished.json to ${GCS_LOGS_PATH} (attempt ${upload_attempt})"
  gsutil -q -h "Content-Type:application/json" cp -a "${gcs_acl}" "${ARTIFACTS}/finished.json" \
    "${GCS_LOGS_PATH}/finished.json" || continue
  break
done

echo "Gubernator linked below:"
echo "https://k8s-gubernator.appspot.com/build/${BUCKET_NAME}/logs/${GCS_JOB_NAME}/${BUILD_STAMP}"

echo "${0} completed successfully at `date`."
