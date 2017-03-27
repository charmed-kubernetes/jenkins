#!/usr/bin/env bash

KUBE_VERSION=${KUBE_VERSION:-"v1.5.2"}

git clone https://github.com/juju-solutions/release.git --branch rye/snaps
cd release/snap && ./docker-build.sh KUBE_VERSION=$KUBE_VERSION
