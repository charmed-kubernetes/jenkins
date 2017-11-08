#!/bin/bash

set -ex
source ./maintenance/helpers-lxc-node.sh

container=${NODE_NAME:-"juju-client-box"}
container_exists $container

RUN rm -rf /root/.local/share/juju/*
PUSH ~/.local/share/juju/accounts.yaml /root/.local/share/juju/
PUSH ~/.local/share/juju/models.yaml /root/.local/share/juju/
PUSH ~/.local/share/juju/controllers.yaml /root/.local/share/juju/
PUSH ~/.local/share/juju/credentials.yaml /root/.local/share/juju/

