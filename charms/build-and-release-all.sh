#!/usr/bin/env bash
set -eux

export CLOUD=aws
export RELEASE=true
export RELEASE_TO_CHANNEL=edge

./charms/build-and-release-easyrsa.sh
./charms/build-and-release-etcd.sh
./charms/build-and-release-flannel.sh
./charms/build-and-release-kubeapi-load-balancer.sh
./charms/build-and-release-kubernetes-master.sh
./charms/build-and-release-kubernetes-worker.sh
./charms/build-and-release-kubernetes-e2e.sh
./charms/build-and-release-calico.sh
./charms/build-and-release-canal.sh
./charms/build-and-release-bundles.sh
