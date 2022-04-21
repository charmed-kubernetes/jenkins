#!/bin/bash
set -eux

if [[ $0 == $BASH_SOURCE ]]; then
  echo "$0 should be sourced";
  exit
fi
echo "sourced ${BASH_SOURCE:-$0}"

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
    tee overlay.yaml <<EOF > /dev/null
series: $SERIES
applications:
  kubernetes-control-plane:
    options:
      channel: $SNAP_VERSION
      controller-manager-extra-args: 'feature-gates=RotateKubeletServerCertificate=true,LegacyServiceAccountTokenNoAutoGeneration=false'
  kubernetes-worker:
    options:
      channel: $SNAP_VERSION
EOF

    juju deploy -m $JUJU_CONTROLLER:$JUJU_MODEL \
          --overlay overlay.yaml \
          --force \
          --channel $JUJU_DEPLOY_CHANNEL $JUJU_DEPLOY_BUNDLE
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

ci_lxc_launch()
{
    # Launch local LXD container to publish to charmcraft
    local lxc_image=$1
    local lxc_container=$2
    sudo lxc launch ${lxc_image} ${lxc_container}
    sleep 10
    sudo lxc shell ${lxc_container} -- bash -c "apt-get update && apt-get install build-essential -y"
}

ci_lxc_delete()
{
    # Stop and delete containers matching a prefix
    local lxc_container_prefix=$1
    local existing_containers=$(sudo lxc list -c n -f csv "${lxc_container_prefix}" | xargs)
    echo "Removing containers: ${existing_containers}"
    set +e
    sudo lxc delete --force "${existing_containers}"
    set -e
}
