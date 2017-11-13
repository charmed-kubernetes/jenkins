#!/bin/bash

set -ex
source ./maintenance/helpers-lxc-node.sh

container=${NODE_NAME:-"juju-client-box"}
container_exists $container

lxc stop $container
lxc delete --force $container
