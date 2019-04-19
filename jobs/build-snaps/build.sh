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
git clone https://github.com/juju-solutions/release.git --branch rye/snaps --depth 1
(
    cd release/snap
    make KUBE_VERSION=$KUBE_VERSION KUBE_ARCH="$KUBE_ARCH" \
         targets="kubeadm kube-apiserver kubectl kubelet kube-proxy kube-scheduler kube-controller-manager kubernetes-test"
)

rm -rf ./cdk-addons
if git ls-remote --exit-code --heads https://github.com/charmed-kubernetes/cdk-addons.git ${ADDONS_BRANCH_VERSION}
then
  echo "Getting cdk-addons from ${ADDONS_BRANCH_VERSION} branch."
  git clone https://github.com/charmed-kubernetes/cdk-addons.git --branch ${ADDONS_BRANCH_VERSION} --depth 1
  if [ "$SKIP_RELEASE_TAG" != "true" ]; then
    tag_release  "charmed-kubernetes" "cdk-addons" ${ADDONS_BRANCH_VERSION} ${GH_USER} ${GH_TOKEN} ${KUBE_VERSION}
  fi
else
  echo "Branch for ${ADDONS_BRANCH_VERSION} does not exist. Getting cdk-addons from master head."
  git clone https://github.com/charmed-kubernetes/cdk-addons.git --depth 1
  if [ "$SKIP_RELEASE_TAG" != "true" ]; then
    tag_release  "charmed-kubernetes" "cdk-addons" "master" ${GH_USER} ${GH_TOKEN} ${KUBE_VERSION}
  fi
fi

# build cdk-addons and track images used by this release
pushd cdk-addons
echo "Building cdk-addons for ${KUBE_VERSION}."
make KUBE_VERSION=${KUBE_VERSION} KUBE_ARCH=${KUBE_ARCH}

echo "Getting list of images that may be used by CDK ${KUBE_VERSION}."
# NB: refactor if we decide to commit directly to master
IMAGES_BRANCH="images-${KUBE_VERSION}"
create_branch "charmed-kubernetes" "bundle" ${GH_USER} ${GH_TOKEN} ${IMAGES_BRANCH}

git clone -b ${IMAGES_BRANCH} https://github.com/charmed-kubernetes/bundle.git
IMAGES_FILE="./bundle/container-images.txt"
STATIC_KEY="${KUBE_VERSION}-static:"
STATIC_LINE=$(grep "^${STATIC_KEY}" ${IMAGES_FILE} 2>/dev/null || echo "")
UPSTREAM_KEY="${KUBE_VERSION}-upstream:"
UPSTREAM_LINE=$(make KUBE_VERSION=${KUBE_VERSION} KUBE_ARCH=${KUBE_ARCH} upstream-images 2>/dev/null | grep "^${UPSTREAM_KEY}")

echo "Updating image list with upstream images."
if grep -q "^${UPSTREAM_KEY}" ${IMAGES_FILE}
then
    sed -i -e "s|^${UPSTREAM_KEY}.*|${UPSTREAM_LINE}|g" ${IMAGES_FILE}
else
    echo ${UPSTREAM_LINE} >> ${IMAGES_FILE}
fi
(
    cd bundle
    git commit -am "Updating ${UPSTREAM_KEY} images"
    git push https://${GH_USER}:${GH_TOKEN}@github.com/charmed-kubernetes/bundle.git ${IMAGES_BRANCH}
)

echo "Pushing images to the Canonical registry"
ALL_IMAGES=$(echo ${STATIC_LINE} ${UPSTREAM_LINE} | sed -e "s|${STATIC_KEY}||g" -e "s|${UPSTREAM_KEY}||g")
for i in ${ALL_IMAGES}
do
    echo "Pushing ${i}"
done
popd

for app in kubeadm kube-apiserver kubectl kubelet kube-proxy kube-scheduler kube-controller-manager kubernetes-test; do
    declare -A kube_arch_to_snap_arch=(
      [ppc64le]=ppc64el
      [arm]=armhf
    )

    retry snapcraft push release/snap/build/${app}_${KUBE_VERSION:1}_"${kube_arch_to_snap_arch[$arch]:-$KUBE_ARCH}".snap --release ${VERSION}/edge
done

retry snapcraft push cdk-addons/cdk-addons_${KUBE_VERSION:1}_"${kube_arch_to_snap_arch[$arch]:-$KUBE_ARCH}".snap --release ${VERSION}/edge
