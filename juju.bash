#!/bin/bash
#
# Juju helpers

function juju::bootstrap::before
{
    echo "> skipping before tasks"
}

function juju::bootstrap::after
{
    echo "> skipping after tasks"
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
            --config caas-image-repo=rocks.canonical.com/cdk/jujusolutions"
    fi
    juju bootstrap "$JUJU_CLOUD" "$JUJU_CONTROLLER" \
         -d "$JUJU_MODEL" \
         --force --bootstrap-series "$SERIES" \
         --bootstrap-constraints arch="amd64" \
         --model-default test-mode=true \
         --model-default resource-tags=owner=k8sci \
         --model-default automatically-retry-hooks=true \
         --model-default logging-config="<root>=DEBUG" \
         $extra_args

    ret=$?
    if (( ret > 0 )); then
        exit "$ret"
    fi
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
    cat <<EOF > overlay.yaml
series: $SERIES
applications:
  kubernetes-control-plane:
    options:
      channel: $SNAP_VERSION
  kubernetes-worker:
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

    ret=$?
    if (( ret > 0 )); then
        exit "$ret"
    fi
}

function juju::wait
{
    echo "Waiting for deployment to settle..."
    timeout 45m juju-wait -e "$JUJU_CONTROLLER:$JUJU_MODEL" -w

    ret=$?
    if (( ret > 0 )); then
        exit "$ret"
    fi
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
