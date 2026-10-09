#!/bin/bash
set -x

THISDIR="$(dirname "$(realpath "$0")")"
. "$THISDIR/cleanup-aws.sh"  # import AWS methods
. "$THISDIR/cleanup-gce.sh"  # import GCE methods

# The purge functions tolerate individual API failures, so a missing CLI would
# otherwise turn every call into "command not found" and still exit 0.
missing=()
for tool in aws jq parallel gcloud; do
    command -v "$tool" >/dev/null || missing+=("$tool")
done
if (( ${#missing[@]} )); then
    echo "ERROR: missing ${missing[*]} on $(hostname); run infra-maintain-* on this agent" >&2
    exit 1
fi

purge::aws
purge::gce

# NOTE: (azure) purge::az is shelved on PS7. The agents have no az CLI (not in
# noble; needs Microsoft's apt repo) and no `az login` session, and no PS7 job
# reaches Azure yet: conformance-arc-ck is blocked on the egress proxy only
# allowing EC2 hosts. Follow-up: once arc runs, install az and log in with the
# service principal from $HOME/.local/share/juju/azure-arc.sh, then restore
# `. "$THISDIR/cleanup-az.sh"` and `purge::az` here.
