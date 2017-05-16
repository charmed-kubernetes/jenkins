#!/usr/bin/env bash
set -eux

BUNDLE_REPOSITORY="https://github.com/juju-solutions/bundle-canonical-kubernetes.git"
git clone ${BUNDLE_REPOSITORY} bundle

bundle/bundle -o ./bundles/cdk-flannel -c edge k8s/cdk cni/flannel
bundle/bundle -o ./bundles/core-flannel -c edge k8s/core cni/flannel

CDK="cs:~containers/bundle/canonical-kubernetes"
CORE="cs:~containers/bundle/kubernetes-core"

PUSH_CMD="/usr/bin/charm push ./bundles/cdk-flannel ${CDK}"
CDK_REVISION=`${PUSH_CMD} | tail -n +1 | head -1 | awk '{print $2}'`
/usr/bin/charm release --channel edge ${CDK_REVISION}
/usr/bin/charm grant --channel edge ${CDK_REVISION} everyone

PUSH_CMD="/usr/bin/charm push ./bundles/core-flannel ${CORE}"
CORE_REVISION=`${PUSH_CMD} | tail -n +1 | head -1 | awk '{print $2}'`
/usr/bin/charm release --channel edge ${CORE_REVISION}
/usr/bin/charm grant --channel edge ${CORE_REVISION} everyone

if [ "$RUN_TESTS" = "true" ]; then
  export CHANNEL="edge"
  export RUN_MATRIX_TESTS=true
  export BUNDLE_NAME="canonical-kubernetes"
  export CLOUD=google
  ./tests/test-bundle.sh
  export CLOUD=aws
  ./tests/test-bundle.sh
  export BUNDLE_NAME="kubernetes-core"
  export CLOUD=google
  ./tests/test-bundle.sh
  export CLOUD=aws
  ./tests/test-bundle.sh

  export FROM_CHANNEL=edge
  export TO_CHANNEL=beta
  ./charms/promote-all-charms-and-bundles.sh
fi
