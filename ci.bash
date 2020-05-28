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

# Run pytest
#
# Returns str: True or False
function test::execute
{
    declare -n is_pass=$1
    timeout 2h pytest \
        --html="report.html" \
        jobs/integration/validation.py \
        --cloud "$JUJU_CLOUD" \
        --model "$JUJU_MODEL" \
        --controller "$JUJU_CONTROLLER"
    ret=$?
    is_pass="True"
    if (( $ret > 0 )); then
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
    tar -cvzf artifacts.tar.gz ci.log _out meta juju-crashdump* report.*
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
        build_starttime=$(timestamp)

        juju::bootstrap::before
        juju::bootstrap
        juju::bootstrap::after
        juju::deploy::before
        juju::deploy
        juju::wait
        juju::deploy::after

        deploy_endtime=$(timestamp)

        test::execute result
        test::report "$result" "$build_starttime" "$deploy_endtime"
        test::capture
        ci::cleanup::before

    } 2>&1 | sed -u -e "s/^/[$log_name_custom] /" | tee -a "ci.log"
}

# get latest python on system
function ci::py
{
    local python_p="python3"

    if [[ -f /usr/bin/python3.6 ]]; then
        python_p="python3.6"
    elif [[ -f /usr/bin/python3.7 ]]; then
        python_p="python3.7"
    fi
    echo "$python_p"
}

# create a virtualenv for python
function ci::venv
{
    declare -n _venv_p=$1
    _venv_p="$TMPDIR/venv"

    rm -rf "$TMPDIR/venv" || true

    virtualenv "$_venv_p" -p "$(ci::py)"
}

# tox environment to use
function ci::toxpy
{
    local python_p="py36"
    if [[ -f /usr/bin/python3.7 ]]; then
        python_p="py37"
    fi
    echo "$python_p"
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
            timeout 2m juju kill-controller -y "$JUJU_CONTROLLER" || true
        fi
    } 2>&1 | sed -u -e "s/^/[$log_name_custom] /" | tee -a "ci.log"
}
trap ci::cleanup EXIT

