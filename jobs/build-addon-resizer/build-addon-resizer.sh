#!/usr/bin/env bash
set -eux

# This script builds the addon-resizer image for multiple architectures and
# pushes them to rocks.canonical.com.
#
# Assumes docker is available on the host environment and has been logged in
# to upload.rocks.canonical.com.

addon_resizer_version="1.8.9"
golang_version="1.12.1"
registry="upload.rocks.canonical.com:5000/cdk"

root_dir="$(readlink -f "$(dirname $0)")"
temp_dir="$root_dir/build-addon-resizer.tmp"

rm -rf "$temp_dir"
mkdir "$temp_dir"
cd "$temp_dir"

wget https://dl.google.com/go/go$golang_version.linux-amd64.tar.gz
tar -xf go$golang_version.linux-amd64.tar.gz
export GOPATH="$temp_dir/gopath"
export PATH="$GOPATH/bin:$temp_dir/go/bin:$PATH"
go version

go get -d k8s.io/autoscaler/addon-resizer
cd "$GOPATH/src/k8s.io/autoscaler/addon-resizer"
git checkout addon-resizer-$addon_resizer_version
git apply "$root_dir/addon-resizer.diff"

make all-push REGISTRY=$registry IMGNAME=addon-resizer

rm -rf "$temp_dir"
