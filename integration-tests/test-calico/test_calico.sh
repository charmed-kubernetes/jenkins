#!/bin/bash
set -eux

# This job expect awscli and juju to be configured

CHARM_CHANNEL=${CHARM_CHANNEL:-"candidate"}

function cleanup {
  juju destroy-controller aws-test-vpc --destroy-all-models -y || true
  ./cleanup-vpc.sh
}
trap cleanup EXIT

./integration-tests/test-calico/bootstrap-single-subnet-aws.sh

# Deploy kubernetes with calico
juju deploy cs:~containers/kubernetes-calico --channel ${CHARM_CHANNEL}
#juju deploy cs:~cynerva/bundle/kubernetes-calico-9

# Deploy e2e and an extra worker for it
juju deploy cs:~containers/kubernetes-e2e --channel ${CHARM_CHANNEL}
juju relate kubernetes-e2e easyrsa
juju relate kubernetes-e2e kubernetes-master:kube-control
juju relate kubernetes-e2e kubernetes-master:kube-api-endpoint

# Disable source-dest-check on all instances
for machine in 0 1 2 3 4 5 6 7 8 9; do
  until juju status --format yaml $machine | grep instance-id | grep -v pending; do sleep 10; done
  INSTANCE_ID=$(juju status --format yaml $machine | grep instance-id | head -n 1 | cut -d " " -f 6)
  aws ec2 modify-instance-attribute --instance-id $INSTANCE_ID --source-dest-check '{"Value": false}'
done

pytest -s ./integration-tests/test_live_model.py
