#!/usr/bin/env bash
set -eux

# Releases a charm with the resources that are currently attached to it.
# $1: charm URL
# $@: remaining arguments to `charm release`, e.g. --channel edge

CHARM="$1"
shift

declare -a RESOURCE_ARGS=()
RESOURCES="$(charm list-resources "$CHARM" | tail -n +3 | sed -e '/^$/d' -e 's/  */-/g')"
for resource in $RESOURCES; do
  RESOURCE_ARGS+=('-r')
  RESOURCE_ARGS+=("$resource")
done

(set +u # allows expansion of empty RESOURCE_ARGS
  charm release "$CHARM" "$@" "${RESOURCE_ARGS[@]}"
)
