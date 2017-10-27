#!/usr/bin/env bash

set -eux

KUBE_VERSION="${KUBE_VERSION:-$(curl -L https://dl.k8s.io/release/stable.txt)}"
KUBE_ARCH="amd64"
ADDONS_BRANCH_VERSION="release-${KUBE_VERSION:1:3}"

source utils/retry.sh
source utilities.sh

rm -rf ./release
git clone https://github.com/juju-solutions/release.git --branch rye/snaps --depth 1
(cd release/snap
  make KUBE_VERSION=$KUBE_VERSION KUBE_ARCH="$KUBE_ARCH" \
    targets="kubeadm kube-apiserver kubectl kubefed kubelet kube-proxy kube-scheduler"
  make KUBE_VERSION=$KUBE_VERSION KUBE_ARCH="amd64" \
    targets="kube-controller-manager kubernetes-test"
)

rm -rf ./cdk-addons
if git ls-remote --exit-code --heads https://github.com/juju-solutions/cdk-addons.git ${ADDONS_BRANCH_VERSION}
then
  git clone https://github.com/juju-solutions/cdk-addons.git --branch ${ADDONS_BRANCH_VERSION} --depth 1
else
  echo "Branch for ${ADDONS_BRANCH_VERSION} does not exist. Getting cdk-addons from master head."
  git clone https://github.com/juju-solutions/cdk-addons.git --depth 1
fi
for arch in $KUBE_ARCH; do
  (cd cdk-addons && make KUBE_VERSION=$KUBE_VERSION KUBE_ARCH=${arch})
done

channel=$(get_major_minor $KUBE_VERSION)
for app in kubeadm kube-apiserver kubectl kubefed kubelet kube-proxy kube-scheduler; do
  for arch in $KUBE_ARCH; do
    retry snapcraft push release/snap/build/${app}_${KUBE_VERSION:1}_${arch}.snap --release ${channel}/edge
  done
done

for app in kube-controller-manager kubernetes-test; do
  retry snapcraft push release/snap/build/${app}_${KUBE_VERSION:1}_amd64.snap --release ${channel}/edge
done

for arch in $KUBE_ARCH; do
  retry snapcraft push cdk-addons/cdk-addons_${KUBE_VERSION:1}_${arch}.snap --release ${channel}/edge
done
