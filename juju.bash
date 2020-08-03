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
    juju bootstrap "$JUJU_CLOUD" "$JUJU_CONTROLLER" \
         -d "$JUJU_MODEL" \
         --bootstrap-series "$SERIES" \
         --force \
         --bootstrap-constraints arch="$ARCH" \
         --model-default test-mode=true \
         --model-default resource-tags=owner=k8sci \
         --model-default image-stream=daily \
         --model-default automatically-retry-hooks=false \
         --model-default logging-config="<root>=DEBUG"
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
  kubernetes-master:
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
}

function juju::wait
{
    echo "Waiting for deployment to settle..."
    timeout 45m juju-wait -e "$JUJU_CONTROLLER:$JUJU_MODEL" -w
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
