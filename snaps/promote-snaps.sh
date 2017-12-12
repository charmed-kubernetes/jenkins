#!/bin/sh
set -eu

# Example usage:
# export PROMOTE_FROM="1.6/edge"
# export PROMOTE_TO="1.6/beta 1.6/candidate edge beta candidate"
# snaps/promote-snaps.sh

SNAPS="kubectl kube-apiserver kube-controller-manager kube-scheduler kubelet kube-proxy cdk-addons kubeadm kubefed kubernetes-test"

ARCH=${KUBE_ARCH:-"amd64"}
echo PROMOTE_FROM="$PROMOTE_FROM"
echo PROMOTE_TO="$PROMOTE_TO"
echo SNAPS="$SNAPS"
echo ARCH="$ARCH"


. utils/retry.sh

for snap in $SNAPS; do
  revisions="$(snapcraft revisions $snap | grep "${ARCH}" | grep " ${PROMOTE_FROM}\*" | cut -d " " -f 1)"
  for rev in $revisions; do
    for target in $PROMOTE_TO; do
      echo snapcraft release $snap $rev $target
      retry snapcraft release $snap $rev $target
    done
  done
done
