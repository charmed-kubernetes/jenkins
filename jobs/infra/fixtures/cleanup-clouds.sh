#!/bin/bash
set -x

THISDIR="$(dirname "$(realpath "$0")")"
. "$THISDIR/cleanup-aws.sh"  # import AWS methods
. "$THISDIR/cleanup-gce.sh"  # import GCE methods
. "$THISDIR/cleanup-az.sh"   # import Azure methods

purge::aws
purge::gce
purge::az
