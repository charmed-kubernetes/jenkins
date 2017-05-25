#!/usr/bin/env bash
set -eux

# Usage: ./tests/run-bundle-tests.sh
#
# Runs CDK bundle tests. This will test CDK using charms, bundles, and snaps
# from the edge channels.
#
# Environment variables:
# TEST_BUNDLES: list of bundles to test (space separated)
# TEST_CONTROLLERS: list of juju controllers to test against (space separated)
# TEST_BUNDLE_CHANNEL: bundle channel to use
# TEST_SNAP_CHANNEL: snap channel to use

TEST_BUNDLES="${TEST_BUNDLES:-canonical-kubernetes}"
TEST_CONTROLLERS="${TEST_CONTROLLERS:-$(juju switch | cut -d ':' -f 1)}"
TEST_BUNDLE_CHANNEL="${TEST_BUNDLE_CHANNEL:-edge}"
TEST_SNAP_CHANNEL="${TEST_SNAP_CHANNEL:-1.6/edge}"

for controller in $TEST_CONTROLLERS; do
  juju switch "$controller"
  for bundle in $TEST_BUNDLES; do
    model="cdk-build-$RANDOM"
    juju add-model "$model" --config test-mode=true
    (trap "juju destroy-model -y $model" EXIT
      rm -rf bundle-under-test
      charm pull canonical-kubernetes --channel "$TEST_BUNDLE_CHANNEL" bundle-under-test
      ./tests/set-snap-channel.py bundle-under-test "$TEST_SNAP_CHANNEL"

      bundletester --no-matrix -vF -l DEBUG -t bundle-under-test -r xml -o bundle-test-results.xml
    )
  done
done
