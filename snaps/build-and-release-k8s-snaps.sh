#!/usr/bin/env bash

set -eux

KUBE_VERSION="${KUBE_VERSION:-$(curl -L https://dl.k8s.io/release/stable.txt)}"
KUBE_ARCH="amd64"

git clone https://github.com/juju-solutions/release.git --branch rye/snaps --depth 1
(cd release/snap
  make KUBE_VERSION=$KUBE_VERSION KUBE_ARCH="$KUBE_ARCH" \
    targets="kubeadm kube-apiserver kubectl kubefed kubelet kube-proxy kube-scheduler"
  make KUBE_VERSION=$KUBE_VERSION KUBE_ARCH="amd64" \
    targets="kube-controller-manager kubernetes-test"
)

git clone https://github.com/juju-solutions/cdk-addons.git --depth 1
for arch in $KUBE_ARCH; do
  (cd cdk-addons && make KUBE_VERSION=$KUBE_VERSION KUBE_ARCH=${arch})
done

for app in kubeadm kube-apiserver kubectl kubefed kubelet kube-proxy kube-scheduler; do
  for arch in $KUBE_ARCH; do
    snapcraft push release/snap/build/${app}_${KUBE_VERSION:1}_${arch}.snap --release ${KUBE_VERSION:1:3}/edge
  done
done

for app in kube-controller-manager kubernetes-test; do
  snapcraft push release/snap/build/${app}_${KUBE_VERSION:1}_amd64.snap --release ${KUBE_VERSION:1:3}/edge
done

for arch in $KUBE_ARCH; do
  snapcraft push cdk-addons/cdk-addons_${KUBE_VERSION:1}_${arch}.snap --release ${KUBE_VERSION:1:3}/edge
done
