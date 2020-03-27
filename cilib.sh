#!/bin/bash
set -eux

setup_env()
{
  ogc-collect set-key 'job_name_custom' "$JUJU_CONTROLLER-$SERIES-$SNAP_VERSION"

  export JUJU_CONTROLLER="$JUJU_CONTROLLER-$(ogc-collect get-key job_id | cut -f1 -d-)"
  export JUJU_MODEL="$JUJU_MODEL-$SERIES-$(ogc-collect get-key job_id | cut -f1 -d-)"

  ogc-collect set-key 'juju_controller' "$JUJU_CONTROLLER"
  ogc-collect set-key 'juju_model' "$JUJU_MODEL"
  ogc-collect set-key 'juju_cloud' "$JUJU_CLOUD"
  ogc-collect set-key 'snap_version' "$SNAP_VERSION"
  ogc-collect set-key 'juju_deploy_channel' "$JUJU_DEPLOY_CHANNEL"
  ogc-collect set-key 'series' "$SERIES"

}


inject_env()
{
    export JUJU_CONTROLLER=$(ogc-collect get-key juju_controller)
    export JUJU_MODEL=$(ogc-collect get-key juju_model)
    export JUJU_CLOUD=$(ogc-collect get-key juju_cloud)
}

collect_env()
{
    juju-crashdump -s -a debug-layer -a config -m "$JUJU_CONTROLLER:$JUJU_MODEL"  -o "$OGC_JOB_WORKDIR"
}

teardown_env()
{
    juju destroy-controller -y --destroy-all-models --destroy-storage "$JUJU_CONTROLLER"
}


unitAddress()
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
