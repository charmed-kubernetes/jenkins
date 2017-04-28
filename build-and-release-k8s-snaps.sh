#!/usr/bin/env bash

set -eux

KUBE_ARCH="amd64 arm64"

git clone https://github.com/juju-solutions/release.git --branch rye/snaps --depth 1
(cd release/snap
  make KUBE_VERSION=$KUBE_VERSION KUBE_ARCH="$KUBE_ARCH" \
    targets="kubeadm kube-apiserver kubectl kubefed kubelet kube-proxy kube-scheduler"
  make KUBE_VERSION=$KUBE_VERSION KUBE_ARCH="amd64" \
    targets="kube-controller-manager kubernetes-test"
)

git clone https://github.com/juju-solutions/cdk-addons.git --depth 1
(cd cdk-addons && make KUBE_VERSION=$KUBE_VERSION)

for app in kubeadm kube-apiserver kubectl kubefed kubelet kube-proxy kube-scheduler; do
  for arch in $KUBE_ARCH; do
    snapcraft push release/snap/build/${app}_${KUBE_VERSION:1}_${arch}.snap --release ${KUBE_VERSION:1:3}/edge
  done
done

for app in kube-controller-manager kubernetes-test; do
  snapcraft push release/snap/build/${app}_${KUBE_VERSION:1}_amd64.snap --release ${KUBE_VERSION:1:3}/edge
done

snapcraft push cdk-addons/build/cdk-addons_${KUBE_VERSION:1}_amd64.snap --release ${KUBE_VERSION:1:3}/edge
