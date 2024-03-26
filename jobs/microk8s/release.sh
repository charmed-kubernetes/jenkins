#!/bin/bash
# shellcheck disable=SC2034,SC1090

set -x

###############################################################################
# INITIALIZE
###############################################################################
: "${WORKSPACE:=$(pwd)}"

. "$WORKSPACE/ci.bash"
. "$WORKSPACE/juju.bash"

###############################################################################
# FUNCTION OVERRIDES
###############################################################################

###############################################################################
# ENV
###############################################################################
export ARCH=${1:-amd64}
export TRACKS=${3:-}
export DRY_RUN=${4:-yes}
export ALWAYS_RELEASE=${5:-no}
export TESTS_BRANCH=${6:-}
export PROXY=${7:-}
CHOSEN_CHANNEL=${2:-all}


SERIES=focal
JUJU_DEPLOY_BUNDLE="${WORKSPACE}/ubuntu.yaml"
JUJU_DEPLOY_CHANNEL=stable
JUJU_CLOUD=aws/us-east-1
JUJU_CONTROLLER=release-$(identifier::short)
JUJU_VERSION=$(juju --version | cut -f-2 -d.)
CUSTOM_CLOUD=$(echo "$JUJU_CLOUD" | cut -f1 -d/)
JOB_NAME_CUSTOM="release-microk8s-$ARCH"
SNAP_VERSION=stable
JOB_ID=$(identifier)
JOB_REPORTING=no

function snapcraft::login
{
    snapcraft login --with "${SNAPCRAFTCREDS}"
}

function gather::channels
{
    if [[ ${CHOSEN_CHANNEL} == "all" ]]; then
        CHANNELS=("beta" "stable" "pre-release")
    else
        CHANNELS=($CHOSEN_CHANNEL)
    fi
    echo "Running for channels ${ARCH}/${CHANNELS}"
}

function juju::deploy::overlay
{
    local constraints
    constraints="cores=8 mem=16G root-disk=80G arch=${ARCH}"
    if [ "${ARCH}" == "amd64" ] && [ "${CHANNEL}" == "stable" ]; then
        constraints+=" instance-type=g3s.xlarge"
    fi

    cat << EOF > $JUJU_DEPLOY_BUNDLE
series: $SERIES
applications:
  ubuntu:
    charm: ubuntu
    channel: latest/stable
    constraints: $constraints
    num_units: 1
EOF
}

function juju::deploy
{
    juju deploy -m "$JUJU_CONTROLLER:$JUJU_MODEL" "$JUJU_DEPLOY_BUNDLE"
    juju::deploy-report $? "model-deploy"
}

function test::execute
{
    local juju_full_model="$JUJU_CONTROLLER:$JUJU_MODEL"
    export JUJU_UNIT=ubuntu/0
    juju ssh -m "${juju_full_model}" --pty=true $JUJU_UNIT -- 'sudo snap install lxd'
    juju ssh -m "${juju_full_model}" --pty=true $JUJU_UNIT -- 'sudo lxd.migrate -yes' || true
    juju ssh -m "${juju_full_model}" --pty=true $JUJU_UNIT -- 'sudo lxd init --auto'
    if [ "${CHANNEL}" == "pre-release" ]; then
        juju ssh -m "${juju_full_model}" --pty=true $JUJU_UNIT -- 'sudo snap install snapcraft --classic'
    fi

    case $CHANNEL in
        beta)
            SCRIPT_NAME="release-to-beta.py"
            ;;
        stable)
            SCRIPT_NAME="release-to-stable.py"
            ;;
        pre-release)
            SCRIPT_NAME="release-pre-release.py"
            ;;
    esac

    declare -n is_pass=$1
    timeout 6h python jobs/microk8s/${SCRIPT_NAME}
    ret=$?
    is_pass="True"
    if (( ret == 124 )); then
        is_pass="Timeout"
    elif (( ret > 0 )); then
        is_pass="False"
    fi
}

###############################################################################
# START
###############################################################################

snapcraft::login
gather::channels
for CHANNEL in "${CHANNELS[@]}"; do
    export "CHANNEL"
    timeout 6h python jobs/microk8s/release-needed.py
    if (( $? == 0 )); then
        JOB_STAGE="${CHANNEL}-${ARCH}"
        JUJU_MODEL="release-microk8s-${JOB_STAGE}-model"
        ci::run
    fi
done
