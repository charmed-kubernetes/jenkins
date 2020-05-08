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
    : "${TMP_DIR:?Must have a temporary directory defined}"
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
    export TMP_DIR
}

function identifier
{
    uuidgen | tr '[:upper:]' '[:lower:]'
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
    TOX_WORK_DIR="$WORKSPACE/.tox" timeout 2h tox -e py36 -- pytest \
                --html="$TMP_DIR/report.html" \
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

    python -c "import json; from datetime import datetime; print(json.dumps({'test_result': $result, 'job_name_custom': '$JOB_NAME_CUSTOM', 'job_name': '$JOB_NAME_CUSTOM', 'job_id': '$JOB_ID', 'build_endtime': datetime.utcnow().isoformat(), 'build_starttime': '$build_starttime', 'deploy_endtime': '$deploy_endtime'}))" | tee "$TMP_DIR/metadata.json"
}


# Entrypoint to start the deployment, testing, reporting
function ci::run
{
    compile::env

    local log_name_custom=$(echo "$JOB_NAME_CUSTOM" | tr '/' '-')
    {
        build_starttime=$(timestamp)

        juju::bootstrap
        juju::deploy
        juju::wait

        deploy_endtime=$(timestamp)

        test::execute result
        test::report "$result" "$build_starttime" "$deploy_endtime"

    } 2>&1 | sed -u -e "s/^/[$log_name_custom] /" | tee "$TMP_DIR/ci.log"
}



# cleanup function
function ci::cleanup
{
    if which juju-crashdump; then
        juju-crashdump -s -a debug-layer -a config -m "$JUJU_CONTROLLER:$JUJU_MODEL" -o "$TMP_DIR"
    fi
    (cd "$TMP_DIR" && tar cvzf artifacts.tar.gz *)
    venv_p="$TMP_DIR/cleanupvenv"
    virtualenv "$venv_p" -p python3.6
    "$venv_p"/bin/python -m pip install awscli columbo
    "$venv_p"/bin/columbo --output-dir "$TMP_DIR/_out" "$TMP_DIR/artifacts.tar.gz" || true
    aws_cli="$venv_p/bin/aws"
    "$aws_cli" s3 cp "$TMP_DIR/_out/columbo-report.json" s3://jenkaas/"$JOB_ID"/columbo-report.json || true
    "$aws_cli" s3 cp "$TMP_DIR/metadata.json" s3://jenkaas/"$JOB_ID"/metadata.json || true
    "$aws_cli" s3 cp "$TMP_DIR/report.html" s3://jenkaas/"$JOB_ID"/index.html || true
    "$aws_cli" s3 cp "$TMP_DIR/artifacts.tar.gz" s3://jenkaas/"$JOB_ID"/artifacts.tar.gz || true

    if ! timeout 2m juju destroy-controller -y --destroy-all-models --destroy-storage "$JUJU_CONTROLLER"; then
            timeout 2m juju kill-controller -y "$JUJU_CONTROLLER" || true
    fi

    rm -rf "$TMP_DIR"
}
trap ci::cleanup EXIT

