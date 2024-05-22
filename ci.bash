#!/bin/bash

# Make sure required environment variables are set and export them
function compile::env
{
    : "${JUJU_CLOUD:?Must have a cloud defined}"
    : "${JUJU_CONTROLLER:?Must have a controller defined}"
    : "${JUJU_DEPLOY_BUNDLE:?Must have a bundle defined}"
    : "${JUJU_DEPLOY_CHANNEL:?Must have a channel defined}"
    : "${JUJU_MODEL:?Must have a model defined}"
    : "${JUJU_UPDATE_STATUS_INTERVAL:=150s}"
    : "${JUJU_OWNER:=k8sci}"
    : "${JOB_STAGE:-}"
    : "${JOB_REPORTING:-yes}"
    : "${SERIES:?Must have a release series defined}"
    : "${SNAP_VERSION:?Must have a snap version defined}"
    : "${JOB_NAME_CUSTOM:?Must have a job name defined}"
    : "${JOB_ID:?Must have a job id defined}"
    : "${KV_DB:=metadata.db}"

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
    juju_channel_format=$(echo "$JUJU_DEPLOY_CHANNEL" | tr '/' '-')
    snap_version_format=$(echo "$SNAP_VERSION" | tr '/' '-')

    touch "meta/name-$job_name_format"
    touch "meta/channel-$juju_channel_format"
    touch "meta/series-$SERIES"
    touch "meta/snap_version-$snap_version_format"
    for i in meta/*; do
        python bin/s3 cp "$i" "$i"
    done

    kv::set "job_id" "$JOB_ID"
    kv::set "job_name" "$JOB_NAME_CUSTOM"
    kv::set "job_name_custom" "$JOB_NAME_CUSTOM"
    kv::set "job_stage" "$JOB_STAGE"
    kv::set "series" "$SERIES"
    kv::set "arch" "$ARCH"
    kv::set "snap_version" "$SNAP_VERSION"
    kv::set "channel" "$JUJU_DEPLOY_CHANNEL"
    kv::set "juju_channel" "$(juju::version)"
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

# sets a state key/value namespaced to the current spell
#
# Arguments:
# $1: KEY
# $2: VALUE
function kv::set
{
    kv-cli "$KV_DB" set "$1" "$2"
}

# gets a state key/value namespaced by the current spell
#
# Arguments:
# $1: KEY
function kv::get
{
    kv-cli "$KV_DB" get "$1" || echo "None"
}

# Run pytest
#
# Returns str: True or False
function test::execute
{
    juju::pip::2.9

    extra_args=''
    if [ -n "$TEST_UPGRADE_SNAPD_CHANNEL" ]; then
        # Azure seems to have trouble with the daily image-stream
        extra_args="${extra_args} \
            --snapd-upgrade \
            --snapd-channel ${TEST_UPGRADE_SNAPD_CHANNEL}"
    fi

    declare -n is_pass=$1
    timeout -s INT 3h pytest \
        --html="report.html" \
        --json-report \
        --json-report-summary \
        --json-report-file="report.json" \
        --full-trace \
        jobs/integration/validation.py \
        --cloud "$JUJU_CLOUD" \
        --model "$JUJU_MODEL" \
        --controller "$JUJU_CONTROLLER" \
        ${extra_args}
    
    ret=$?
    is_pass="True"
    if (( ret == 124 )); then
        is_pass="Timeout"
    elif (( ret > 0 )); then
        is_pass="False"
    fi
}

# store test report
function test::report
{
    result=$1
    kv::set "result" "$result"
    touch "meta/result-$result"
    if [ "${JOB_REPORTING}" == "no" ]; then
        echo "Job reporting disabled"
    else
        python bin/s3 cp "meta/result-$result" "meta/result-$result"
    fi
}

function test::capture
{
    if [ "${JOB_REPORTING}" == "no" ]; then
        echo "Job reporting disabled"
        return 0
    fi

    if which juju-crashdump; then
        # -s                     small crashdump by skipping /var/lib/juju
        # -a debug-layer         included debug-layer addon
        # -a config              included config addon
        # -j snap.kube*          included logs from all kube* daemons
        # -j snap.cdk-addons*    included logs from cdk-addons*
        juju-crashdump \
            -s \
            -a debug-layer \
            -a config \
            -j snap.kube-apiserver.daemon \
            -j snap.kube-controller-manager.daemon \
            -j snap.kube-proxy.daemon \
            -j snap.kube-scheduler.daemon \
            -j snap.kubelet.daemon \
            -j snap.cdk-addons* \
            -m "$JUJU_CONTROLLER:$JUJU_MODEL"
    fi
    tar -cvzf artifacts.tar.gz ci.log _out meta juju-crashdump* report.* failures* logs/ || true
    /usr/local/bin/columbo -r columbo.yaml -o "_out" "artifacts.tar.gz" || true
    python bin/s3 cp "columbo-report.json" columbo-report.json || true

    python -c "import json; import kv; print(json.dumps(dict(kv.KV('metadata.db'))))" | tee "metadata.json"
    python bin/s3 cp "metadata.json" metadata.json || true
    python bin/s3 cp "report.html" report.html || true
    python bin/s3 cp "report.json" report.json || true
    python bin/s3 cp "metadata.db" metadata.db || true
    python bin/s3 cp "artifacts.tar.gz" artifacts.tar.gz || true

    # Generate job report
    python bin/report job-result --job-id "$JOB_ID" --metadata-db metadata.db --columbo-json columbo-report.json

    echo "@@@ CAPTURE RESULTS @@@"
    echo "@"
    echo "@  http://jenkaas.s3-website-us-east-1.amazonaws.com/$JOB_ID/artifacts.tar.gz"
    echo "@"
    echo "@@@"
}


# Entrypoint to start the deployment, testing, reporting
function ci::run
{
    compile::env

    local log_name_custom=$(echo "$JOB_NAME_CUSTOM" | tr '/' '-')
    {
        kv::set "build_starttime" "$(timestamp)"

        juju::bootstrap::before
        juju::bootstrap
        juju::bootstrap::after
        juju::model::speed-up
        juju::deploy::before
        juju::deploy::overlay
        juju::deploy
        juju::wait

        juju::deploy::after

        test::execute result

        kv::set "build_endtime" "$(timestamp)"

        test::report "$result"

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

function ci::cleanup::model::addons
{
    if ! timeout 10m juju destroy-model --no-prompt --destroy-storage "$JUJU_CONTROLLER:addons"; then
      timeout 10m juju destroy-model --no-prompt --destroy-storage "$JUJU_CONTROLLER:addons" --force
    fi
}

function ci::cleanup::after
{
    echo "> skipping after tasks"
}

# cleanup function
function ci::cleanup
{
    local log_name_custom=$(echo "$JOB_NAME_CUSTOM" | tr '/' '-')
    {
        ci::cleanup::before || true
        test::capture || true

        juju::destroy
        ci::cleanup::after || true
    } 2>&1 | sed -u -e "s/^/[$log_name_custom] /" | tee -a "ci.log"
}
trap ci::cleanup EXIT

