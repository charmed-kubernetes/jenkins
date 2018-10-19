#!/bin/bash
#

# This script, apart from building and releasing the k8s snaps, will also
# tag the cdk-addons with the release. If a branch exists for the release
# we will build and release from that branch. If no branch exists, we will
# build from master.
# GH_USER and GH_TOKEN are the user and token that will touch the repo.

set -eux

scripts_path=$(dirname "$0")
KUBE_VERSION="${KUBE_VERSION:-$(curl -L https://dl.k8s.io/release/stable.txt)}"
SKIP_RELEASE_TAG="${SKIP_RELEASE_TAG:-false}"

source $scripts_path/utilities.sh
VERSION=$(get_major_minor $KUBE_VERSION)
ADDONS_BRANCH_VERSION="release-${VERSION}"

source $scripts_path/retry.sh

sudo rm -rf ./release
#git clone https://github.com/juju-solutions/release.git --branch rye/snaps --depth 1
git clone https://github.com/battlemidget/release.git --branch alt-arch-builds --depth 1
(
    cd release/snap
    make KUBE_VERSION=$KUBE_VERSION KUBE_ARCH="$KUBE_ARCH" \
         targets="kubeadm kube-apiserver kubectl kubelet kube-proxy kube-scheduler kube-controller-manager kubernetes-test"
)

rm -rf ./cdk-addons
if git ls-remote --exit-code --heads https://github.com/juju-solutions/cdk-addons.git ${ADDONS_BRANCH_VERSION}
then
  echo "Getting cdk-addons from ${ADDONS_BRANCH_VERSION} branch."
  git clone https://github.com/juju-solutions/cdk-addons.git --branch ${ADDONS_BRANCH_VERSION} --depth 1
  if [ "$SKIP_RELEASE_TAG" != "true" ]; then
    tag_release  "juju-solutions" "cdk-addons" ${ADDONS_BRANCH_VERSION} ${GH_USER} ${GH_TOKEN} ${KUBE_VERSION}
  fi
else
  echo "Branch for ${ADDONS_BRANCH_VERSION} does not exist. Getting cdk-addons from master head."
  git clone https://github.com/juju-solutions/cdk-addons.git --depth 1
  if [ "$SKIP_RELEASE_TAG" != "true" ]; then
    tag_release  "juju-solutions" "cdk-addons" "master" ${GH_USER} ${GH_TOKEN} ${KUBE_VERSION}
  fi
fi

(cd cdk-addons && make KUBE_VERSION=$KUBE_VERSION KUBE_ARCH=${KUBE_ARCH})

for app in kubeadm kube-apiserver kubectl kubelet kube-proxy kube-scheduler kube-controller-manager kubernetes-test; do
    retry snapcraft push release/snap/build/${app}_${KUBE_VERSION:1}_${KUBE_ARCH}.snap --release ${VERSION}/edge
done

retry snapcraft push cdk-addons/cdk-addons_${KUBE_VERSION:1}_${KUBE_ARCH}.snap --release ${VERSION}/edge
