#!/usr/bin/env bash

set -o errexit  # Exit when an individual command fails.
set -o pipefail  # The exit status of the last command is returned.

OS=${OS:-"linux"}
ARCH=${ARCH:-"amd64"}

rm -rf kubernetes
git clone https://github.com/kubernetes/kubernetes.git

cd kubernetes
export KUBE_VERSION=`git describe --dirty`

# Grab the user id and group id of this current user.
GROUP_ID=$(id -g)
USER_ID=$(id -u)

docker run \
  --rm \
  -e "GOOS=${OS}" \
  -e "GOARCH=${ARCH}" \
  -v "${PWD}":/kubernetes \
  golang:1.7.0 \
  /bin/bash -c "cd /kubernetes/cmd/kubeadm && go get k8s.io/kubernetes/cmd/kubeadm/app && go build && chown -R ${USER_ID}:${GROUP_ID} kubeadm"

git clone https://github.com/juju-solutions/release.git --branch rye/snaps --depth 1
mkdir release/snap/kube_bins
cp cmd/kubeadm/kubeadm release/snap/kube_bins

cd release/snap && ./docker-build.sh KUBE_VERSION=${KUBE_VERSION} KUBE_SNAP_BINS=kube_bins kubeadm
