#!/bin/bash
#
# Juju helpers

vergte() {
    [  "$2" = "`echo -e "$1\n$2" | sort -V | head -n1`" ]
}

verlte() {
    [  "$1" = "`echo -e "$1\n$2" | sort -V | head -n1`" ]
}

verlt() {
    [ "$1" = "$2" ] && return 1 || verlte $1 $2
}

function juju::base::from_series
{
    case "$1" in
        "noble")  echo "ubuntu@24.04";;
        "jammy")  echo "ubuntu@22.04";;
        "focal")  echo "ubuntu@20.04";;
        "bionic") echo "ubuntu@18.04";;
        *) 
          test::report "unknown series=$1"
          exit 1
        ;;
    esac
}

function juju::bootstrap::before
{
    echo "> skipping before tasks"
}

function juju::bootstrap::after
{
    echo "> skipping after tasks"
}

function juju::model::speed-up
{
    # Override the update-status hook rather than the default of 5m
    echo "> Setting update-status-hook-interval=${JUJU_UPDATE_STATUS_INTERVAL}"
    juju model-config -m "$JUJU_CONTROLLER:$JUJU_MODEL" update-status-hook-interval="${JUJU_UPDATE_STATUS_INTERVAL}"
}

function juju::version
{
    # yields the short sem version of juju
    # "3.1.0-genericlinux-amd64" becomes "3.1"
    juju --version|cut -f-2 -d.
}

function juju::version_2
{
    verlt $(juju::version) 3.0.0
}

function juju::version_3
{
    vergte $(juju::version) 3.0.0
}

function juju::pip::2.9
{
    # Pin python libjuju to operate with juju 2.9
    if juju::version_2; then
        echo "juju 2.9 environment detected"
        echo "Pinning back python libjuju before starting tests"
        venv/bin/tox --recreate -e juju29 --notest

        source .tox/juju29/bin/activate
    fi
}

function juju::destroy
{
    if ! timeout 2m juju destroy-controller --no-prompt --destroy-all-models --destroy-storage "$JUJU_CONTROLLER"; then
        timeout 10m juju kill-controller -t 2m0s --no-prompt "$JUJU_CONTROLLER" || true
    fi
}

function juju::bootstrap
{
    extra_args='--model-default image-stream=daily'
    if [ "$JUJU_CLOUD" = "azure/centralus" ]; then
        # Azure seems to have trouble with the daily image-stream
        extra_args=''
    fi
    if [ "$JUJU_CLOUD" = "vsphere/Boston" ]; then
        extra_args="$extra_args \
            --model-default datastore=vsanDatastore \
            --model-default primary-network=VLAN_2763 \
            --model-default force-vm-hardware-version=17 \
            --config caas-image-repo=rocks.canonical.com/cdk/jujusolutions \
            --bootstrap-image=juju-ci-root/templates/$SERIES-test-template"
    fi
    if juju::version_2; then
        add_model=("-d ${JUJU_MODEL}")
    else
        add_model=("--add-model ${JUJU_MODEL}")
    fi

    juju::destroy
    TAGS="owner=${JUJU_OWNER} job=${JOB_NAME_CUSTOM}"
    if [ "${JOB_STAGE}" ]; then TAGS+=" stage=${STAGE}"; fi
    juju bootstrap "$JUJU_CLOUD" "$JUJU_CONTROLLER" \
         ${add_model[@]} \
         --debug \
         --force \
         --bootstrap-base "$(juju::base::from_series $SERIES)" \
         --bootstrap-constraints arch="${ARCH:-amd64}" \
         --model-default test-mode=true \
         --model-default resource-tags="${TAGS}" \
         --model-default automatically-retry-hooks=true \
         --model-default logging-config="<root>=DEBUG" \
         $extra_args

    juju::deploy-report $? "bootstrap"
}

function juju::deploy::before
{
    echo "> skipping before tasks"
}

function juju::deploy::after
{
    echo "> skipping after tasks"
}

function juju::deploy::overlay
{
    local constraints
    constraints="arch=${ARCH:-amd64} cores=2 mem=8G root-disk=16G"

    cat <<EOF > overlay.yaml
series: null
default-base: $(juju::base::from_series $SERIES)
applications:
  kubernetes-control-plane:
    constraints: $constraints
    options:
      channel: $SNAP_VERSION
  kubernetes-worker:
    constraints: $constraints
    options:
      channel: $SNAP_VERSION
EOF
}

function juju::deploy
{
    juju deploy -m "$JUJU_CONTROLLER:$JUJU_MODEL" \
         --overlay overlay.yaml \
         --force \
         --channel "$JUJU_DEPLOY_CHANNEL" "$JUJU_DEPLOY_BUNDLE"

    juju::deploy-report $? "model-deploy"
}

function juju::wait
{
    echo "Waiting for deployment to settle..."
    timeout 60m juju-wait -e "$JUJU_CONTROLLER:$JUJU_MODEL" -w

    juju::deploy-report $? "model-wait"
}

function juju::unitAddress
{
    py_script="
import sys
import yaml

status_yaml=yaml.safe_load(sys.stdin)
unit = status_yaml['applications']['$1']['units']
units = list(unit.keys())
print(unit[units[0]]['public-address'])
"
    juju status -m "$JUJU_CONTROLLER:$JUJU_MODEL" "$1" --format yaml | env python3 -c "$py_script"
}

function juju::deploy-report
{
    # report deployment failure
    local ret=$1
    local stage=${2:unspecified}

    local is_pass="True"
    if (( ret == 124 )); then
        is_pass="Timeout"
    elif (( ret > 0 )); then
        is_pass="False"
    fi
    kv::set "deploy_result" "${is_pass}"
    kv::set "deploy_endtime" "$(timestamp)"
    kv::set "deploy_stage" "${stage}"
    touch "meta/deployresult-${is_pass}"
    python bin/s3 cp "meta/deployresult-${is_pass}" "meta/deployresult-${is_pass}"

    if (( ret > 0 )); then
        test::report ${is_pass}
        exit $ret
    fi
}
