#!/usr/bin/env bash

set -eux

git clone https://github.com/juju-solutions/release.git --branch rye/snaps --depth 1
cd release/snap && ./docker-build.sh KUBE_VERSION=$KUBE_VERSION
