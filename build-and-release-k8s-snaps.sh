#!/usr/bin/env bash

set -eux

git clone https://github.com/juju-solutions/release.git --branch rye/snaps --depth 1
cd release/snap && make KUBE_VERSION=$KUBE_VERSION

for app in kubeadm kube-apiserver kube-controller-manager kubectl kubefed kubelet kube-proxy kube-scheduler; do
  snapcraft push build/${app}_${KUBE_VERSION:1}_amd64.snap --release ${KUBE_VERSION:1:3}/edge
done
