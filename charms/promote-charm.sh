#!/usr/bin/env bash
set -eux

# Usage: CHARM=<charm> FROM_CHANNEL=<channel> TO_CHANNEL=<channel> ./charms/promote-charm.sh
#
# Promotes a charm from one channel to another, including its resources.

if [ -z "$CHARM" ]; then
  echo "CHARM environment variable is required"
  exit 1
elif [ -z "$FROM_CHANNEL" ]; then
  echo "FROM_CHANNEL environment variable is required"
  exit 1
elif [ -z "$TO_CHANNEL" ]; then
  echo "TO_CHANNEL environment variable is required"
  exit 1
fi

CHARM_ID="$(charm show "$CHARM" --channel "$FROM_CHANNEL" id | grep Id: | awk '{print $2}')"

declare -a RESOURCE_ARGS=()
RESOURCES="$(charm list-resources "$CHARM_ID" --channel "$FROM_CHANNEL" --format=short | sed '/No resources found./d')"
for resource in $RESOURCES; do
  RESOURCE_ARGS+=('-r')
  RESOURCE_ARGS+=("$resource")
done

(set +u # allows expansion of empty RESOURCE_ARGS
  charm release "$CHARM_ID" --channel "$TO_CHANNEL" "${RESOURCE_ARGS[@]}"
)
