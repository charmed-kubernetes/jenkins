#!/bin/bash
set -eux

# Disable source-dest-check on all instances
MACHINES_CSV=$(juju status -m "$CONTROLLER:$MODEL" --format json | jq -r '.machines | keys | @csv' | tr -d \")
IFS=$','
for machine in $MACHINES_CSV; do
  until juju status -m "$CONTROLLER:$MODEL" --format yaml "$machine" | grep instance-id | grep -v pending; do sleep 10; done
  INSTANCE_ID=$(juju status -m "$CONTROLLER:$MODEL" --format yaml "$machine" | grep instance-id | head -n 1 | cut -d " " -f 6)
  aws ec2 modify-instance-attribute --instance-id "$INSTANCE_ID" --source-dest-check '{"Value": false}'
done
