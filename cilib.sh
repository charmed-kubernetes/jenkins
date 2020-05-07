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
    cp ogc.log "$OGC_JOB_WORKDIR" || true
    cp *.xml "$OGC_JOB_WORKDIR" || true
    cp *.html "$OGC_JOB_WORKDIR" || true

    # Run at end of collection
    ogc-collect stats
    aws s3 cp "$OGC_JOB_WORKDIR"/metadata.json s3://jenkaas/"$OGC_JOB_ID"/metadata.json || true
    aws s3 cp report.html s3://jenkaas/"$OGC_JOB_ID"/index.html || true
}

teardown_env()
{
    juju destroy-controller -y --destroy-all-models --destroy-storage "$JUJU_CONTROLLER"
}

bootstrap_env()
{
    juju bootstrap $JUJU_CLOUD $JUJU_CONTROLLER \
         -d $JUJU_MODEL \
         --bootstrap-series $SERIES \
         --force \
         --bootstrap-constraints arch=$ARCH \
         --model-default test-mode=true \
         --model-default resource-tags=owner=k8sci \
         --model-default image-stream=daily
}

deploy_env()
{
    tee overlay.yaml <<EOF> /dev/null
series: $SERIES
applications:
  kubernetes-master:
    options:
      channel: $SNAP_VERSION
  kubernetes-worker:
    options:
      channel: $SNAP_VERSION
EOF

    juju deploy -m $JUJU_CONTROLLER:$JUJU_MODEL \
          --overlay overlay.yaml \
          --force \
          --channel $JUJU_DEPLOY_CHANNEL $JUJU_DEPLOY_BUNDLE
}

wait_env()
{
    timeout 45m juju-wait -e $JUJU_CONTROLLER:$JUJU_MODEL -w
    ogc-collect set-key 'deploy_endtime' "env python3 -c 'import datetime; print(str(datetime.datetime.utcnow().isoformat()))'"
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

# Grabs current directory housing script ($0)
#
# Arguments:
# $0: current script
scriptPath() {
    env python3 -c "import os,sys; print(os.path.dirname(os.path.abspath(\"$0\")))"
}
