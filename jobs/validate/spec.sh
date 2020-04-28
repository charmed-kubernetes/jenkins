#!/bin/bash

ID=$(uuid | cut -f1 -d-)
export SNAP_VERSION=$1
export SERIES=$2
export JUJU_DEPLOY_BUNDLE=cs:~containers/charmed-kubernetes
export JUJU_DEPLOY_CHANNEL=edge
export JUJU_CLOUD=aws/us-east-2
export JUJU_CONTROLLER=validate-stokes-$ID
export JUJU_MODEL=validate-stokes
export ARCH=amd64

function cleanup
{
    if ! timeout 2m juju destroy-controller -y --destroy-all-models --destroy-storage "$JUJU_CONTROLLER"; then
            timeout 2m juju kill-controller -y "$JUJU_CONTROLLER"
    fi
}
trap cleanup EXIT


{
    juju bootstrap $JUJU_CLOUD $JUJU_CONTROLLER \
         -d $JUJU_MODEL \
         --bootstrap-series $SERIES \
         --force \
         --bootstrap-constraints arch=$ARCH \
         --model-default test-mode=true \
         --model-default resource-tags=owner=k8sci \
         --model-default image-stream=daily

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

    echo "Waiting for deployment to settle..."
    timeout 45m juju-wait -e $JUJU_CONTROLLER:$JUJU_MODEL -w

    timeout 2h tox --workdir .tox -e py3 -- pytest \
            $WORKSPACE/jobs/integration/validation.py \
            --cloud $JUJU_CLOUD \
            --model $JUJU_MODEL \
            --controller $JUJU_CONTROLLER

    ret=$?
    echo $ret > job-$ID-result.txt

    exit $ret

} 2>&1 | sed -u -e "s/^/[$JUJU_CONTROLLER] /" | tee $JUJU_CONTROLLER.log
