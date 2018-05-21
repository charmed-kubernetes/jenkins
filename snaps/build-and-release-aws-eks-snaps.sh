#!/usr/bin/env bash
#

# This script will build and release snaps for AWS EKS.
set -eux

EKS_RELEASE="${EKS_RELEASE:-edge/eks.0}"
KUBE_VERSION="${KUBE_VERSION:-$(curl -L https://dl.k8s.io/release/stable.txt)}"
KUBE_ARCH="amd64"

source utilities.sh
MAIN_VERSION=$(get_major_minor $KUBE_VERSION)

source utils/retry.sh

rm -rf ./release
git clone https://github.com/juju-solutions/release.git --branch rye/snaps --depth 1
(cd release/snap
  make KUBE_VERSION=$KUBE_VERSION KUBE_ARCH="$KUBE_ARCH" \
    targets="kubectl kubelet kube-proxy"
  make KUBE_VERSION=$KUBE_VERSION KUBE_ARCH="amd64" \
    targets="kubernetes-test"
)

for app in kubectl kubelet kube-proxy; do
  for arch in $KUBE_ARCH; do
    retry snapcraft push release/snap/build/${app}_${KUBE_VERSION:1}_${arch}.snap --release ${MAIN_VERSION}/${EKS_RELEASE}
  done
done

retry snapcraft push release/snap/build/kubernetes-test_${KUBE_VERSION:1}_amd64.snap --release ${MAIN_VERSION}/${EKS_RELEASE}
