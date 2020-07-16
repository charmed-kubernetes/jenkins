#!/bin/bash

# Make sure required environment variables are set and export them
function compile::env
{
    : "${JUJU_CLOUD:?Must have a cloud defined}"
    : "${JUJU_CONTROLLER:?Must have a controller defined}"
    : "${JUJU_DEPLOY_BUNDLE:?Must have a bundle defined}"
    : "${JUJU_DEPLOY_CHANNEL:?Must have a channel defined}"
    : "${JUJU_MODEL:?Must have a model defined}"
    : "${SERIES:?Must have a release series defined}"
    : "${SNAP_VERSION:?Must have a snap version defined}"
    : "${JOB_NAME_CUSTOM:?Must have a job name defined}"
    : "${JOB_ID:?Must have a job id defined}"

    export ARCH
    export JOB_NAME_CUSTOM
    export JOB_ID
    export JUJU_CLOUD
    export JUJU_CONTROLLER
    export JUJU_DEPLOY_BUNDLE
    export JUJU_DEPLOY_CHANNEL
    export JUJU_MODEL
    export SERIES
    export SNAP_VERSION

    echo "Storing initial meta information"
    local job_name_format
    local snap_version_format

    test -d "meta" && rm -rf "meta"
    mkdir -p "meta"

    job_name_format=$(echo "$JOB_NAME_CUSTOM" | tr '/' '-')
    snap_version_format=$(echo "$SNAP_VERSION" | tr '/' '-')

    touch "meta/name-$job_name_format"
    touch "meta/channel-$JUJU_DEPLOY_CHANNEL"
    touch "meta/series-$SERIES"
    touch "meta/snap_version-$snap_version_format"
    for i in meta/*; do
        python bin/s3 cp "$i" "$i"
    done
}

function identifier
{
    uuidgen | tr '[:upper:]' '[:lower:]'
}

function identifier::short
{
    uuidgen | tr '[:upper:]' '[:lower:]' | cut -f1 -d-
}

# Generate a isoformat timetsamp
function timestamp
{
    python -c "from datetime import datetime; print(datetime.utcnow().isoformat())"
}

# Retry a command up to a specific numer of times until it exits successfully,
# with exponential back off.
#
#  $ retry 5 echo Hello
#  Hello
#
#  $ retry 5 false
#  Retry 1/5 exited 1, retrying in 1 seconds...
#  Retry 2/5 exited 1, retrying in 2 seconds...
#  Retry 3/5 exited 1, retrying in 4 seconds...
#  Retry 4/5 exited 1, retrying in 8 seconds...
#  Retry 5/5 exited 1, no more retries left.
#  ref: https://gist.github.com/sj26/88e1c6584397bb7c13bd11108a579746
function retry {
  local retries=$1
  shift

  local count=0
  until "$@"; do
    exit=$?
    wait=$((2 ** count))
    count=$((count + 1))
    if [ "$count" -lt "$retries" ]; then
      echo "Retry $count/$retries exited $exit, retrying in $wait seconds..."
      sleep $wait
    else
      echo "Retry $count/$retries exited $exit, no more retries left."
      return $exit
    fi
  done
  return 0
}

# Run pytest
#
# Returns str: True or False
function test::execute
{
    declare -n is_pass=$1
    timeout 3h pytest \
        --html="report.html" \
        jobs/integration/validation.py \
        --cloud "$JUJU_CLOUD" \
        --model "$JUJU_MODEL" \
        --controller "$JUJU_CONTROLLER"
    ret=$?
    is_pass="True"
    if (( ret > 0 )); then
        is_pass="False"
    fi
}

# store test report
function test::report
{
    result=$1
    build_starttime=$2
    deploy_endtime=$3

    python -c "import json; from datetime import datetime; print(json.dumps({'test_result': $result, 'job_name_custom': '$JOB_NAME_CUSTOM', 'job_name': '$JOB_NAME_CUSTOM', 'job_id': '$JOB_ID', 'build_endtime': datetime.utcnow().isoformat(), 'build_starttime': '$build_starttime', 'deploy_endtime': '$deploy_endtime'}))" | tee "metadata.json"
    touch "meta/result-$result"
    python bin/s3 cp "meta/result-$result" "meta/result-$result"
}

function test::capture
{
    if which juju-crashdump; then
        juju-crashdump -s -a debug-layer -a config -m "$JUJU_CONTROLLER:$JUJU_MODEL"
    fi
    tar -cvzf artifacts.tar.gz ci.log _out meta juju-crashdump* report.* failures*
    columbo --output-dir "_out" "artifacts.tar.gz" || true
    python bin/s3 cp "_out/columbo-report.json" columbo-report.json || true
    python bin/s3 cp "metadata.json" metadata.json || true
    python bin/s3 cp "report.html" report.html || true
    python bin/s3 cp "artifacts.tar.gz" artifacts.tar.gz || true
}


# Entrypoint to start the deployment, testing, reporting
function ci::run
{
    compile::env

    local log_name_custom=$(echo "$JOB_NAME_CUSTOM" | tr '/' '-')
    {
        ci::sleep
        build_starttime=$(timestamp)

        juju::bootstrap::before
        retry 5 juju::bootstrap
        juju::bootstrap::after

        ci::sleep
        juju::deploy::before
        retry 5 juju::deploy
        juju::wait
        juju::deploy::after

        deploy_endtime=$(timestamp)

        test::execute result
        test::report "$result" "$build_starttime" "$deploy_endtime"
        test::capture
        ci::cleanup::before

    } 2>&1 | sed -u -e "s/^/[$log_name_custom] /" | tee -a "ci.log"
}

# injects random sleep
function ci::sleep
{
    sleep $(( ( RANDOM % 25 )  + 1 ))s
}

function ci::cleanup::before
{
    echo "> skipping before tasks"
}

# cleanup function
function ci::cleanup
{
    local log_name_custom=$(echo "$JOB_NAME_CUSTOM" | tr '/' '-')
    {
        if ! timeout 2m juju destroy-controller -y --destroy-all-models --destroy-storage "$JUJU_CONTROLLER"; then
            timeout 5m juju kill-controller -y "$JUJU_CONTROLLER" || true
        fi
    } 2>&1 | sed -u -e "s/^/[$log_name_custom] /" | tee -a "ci.log"
}
trap ci::cleanup EXIT

