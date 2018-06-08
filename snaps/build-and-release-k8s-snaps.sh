#!/usr/bin/env bash
#

# This script, apart from building and releasing the k8s snaps, will also
# tag the cdk-addons with the release. If a branch exists for the release
# we will build and release from that branch. If no branch exists, we will
# build from master.
# GH_USER and GH_TOKEN are the user and token that will touch the repo.

set -eux

KUBE_VERSION="${KUBE_VERSION:-$(curl -L https://dl.k8s.io/release/stable.txt)}"
KUBE_ARCH="amd64"

source utilities.sh
VERSION=$(get_major_minor $KUBE_VERSION)
ADDONS_BRANCH_VERSION="release-${VERSION}"

source utils/retry.sh

rm -rf ./release
git clone https://github.com/juju-solutions/release.git --branch rye/snaps --depth 1
(cd release/snap
  make KUBE_VERSION=$KUBE_VERSION KUBE_ARCH="$KUBE_ARCH" \
    targets="kubeadm kube-apiserver kubectl kubelet kube-proxy kube-scheduler"
  make KUBE_VERSION=$KUBE_VERSION KUBE_ARCH="amd64" \
    targets="kube-controller-manager kubernetes-test"
)

rm -rf ./cdk-addons
if git ls-remote --exit-code --heads https://github.com/juju-solutions/cdk-addons.git ${ADDONS_BRANCH_VERSION}
then
  echo "Getting cdk-addons from ${ADDONS_BRANCH_VERSION} branch."
  git clone https://github.com/juju-solutions/cdk-addons.git --branch ${ADDONS_BRANCH_VERSION} --depth 1
  tag_release  "juju-solutions" "cdk-addons" ${ADDONS_BRANCH_VERSION} ${GH_USER} ${GH_TOKEN} ${KUBE_VERSION}
else
  echo "Branch for ${ADDONS_BRANCH_VERSION} does not exist. Getting cdk-addons from master head."
  git clone https://github.com/juju-solutions/cdk-addons.git --depth 1
  tag_release  "juju-solutions" "cdk-addons" "master" ${GH_USER} ${GH_TOKEN} ${KUBE_VERSION}
fi
for arch in $KUBE_ARCH; do
  (cd cdk-addons && make KUBE_VERSION=$KUBE_VERSION KUBE_ARCH=${arch})
done

for app in kubeadm kube-apiserver kubectl kubelet kube-proxy kube-scheduler; do
  for arch in $KUBE_ARCH; do
    retry snapcraft push release/snap/build/${app}_${KUBE_VERSION:1}_${arch}.snap --release ${MAIN_VERSION}/edge
  done
done

for app in kube-controller-manager kubernetes-test; do
  retry snapcraft push release/snap/build/${app}_${KUBE_VERSION:1}_amd64.snap --release ${MAIN_VERSION}/edge
done

for arch in $KUBE_ARCH; do
  retry snapcraft push cdk-addons/cdk-addons_${KUBE_VERSION:1}_${arch}.snap --release ${MAIN_VERSION}/edge
done
