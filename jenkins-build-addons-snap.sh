#!/usr/bin/env bash

git clone https://github.com/juju-solutions/cdk-addons.git --depth 1
cd cdk-addons && make KUBE_VERSION=$KUBE_VERSION docker
