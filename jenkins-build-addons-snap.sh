#!/usr/bin/env bash

KUBE_VERSION=${KUBE_VERSION:-"v1.5.2"}

git clone https://github.com/juju-solutions/cdk-addons.git
cd cdk-addons && make KUBE_VERSION=$KUBE_VERSION docker
