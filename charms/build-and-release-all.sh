#!/usr/bin/env bash
set -eux

./charms/build-and-release-easyrsa.sh
./charms/build-and-release-etcd.sh
./charms/build-and-release-flannel.sh
./charms/build-and-release-kubeapi-load-balancer.sh
./charms/build-and-release-kubernetes-master.sh
./charms/build-and-release-kubernetes-worker.sh
./charms/build-and-release-kubernetes-e2e.sh
./charms/build-and-release-bundles.sh
