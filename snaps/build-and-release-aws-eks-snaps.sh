#!/usr/bin/env bash
#

# This script will build and release snaps for AWS EKS.
set -eux

EKS_RELEASE="${EKS_RELEASE:-edge}"
KUBE_VERSION="${KUBE_VERSION:-$(curl -L https://dl.k8s.io/release/stable.txt)}"
KUBE_ARCH="amd64"
export SNAP_SUFFIX="eks"

source utilities.sh
source utils/retry.sh

rm -rf ./release
git clone https://github.com/juju-solutions/release.git --branch rye/snaps --depth 1
(cd release/snap
  make KUBE_VERSION=$KUBE_VERSION KUBE_ARCH="$KUBE_ARCH" \
    targets="kubectl kubelet kube-proxy kubernetes-test"
)

# Ensure we are the correct user
if ! $(snapcraft whoami | grep -q canonical-cloud-snaps); then
  echo "Cannot release CPC snaps (wrong user)"
  exit 1
fi
for app in kubectl-eks kubelet-eks kube-proxy-eks kubernetes-test-eks; do
  for arch in $KUBE_ARCH; do
    retry snapcraft push release/snap/build/${app}_${KUBE_VERSION:1}_${arch}.snap --release ${EKS_RELEASE}
  done
done
