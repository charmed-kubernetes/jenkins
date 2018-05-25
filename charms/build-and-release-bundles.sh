#!/usr/bin/env bash
set -eux

BUNDLE_REPOSITORY="https://github.com/juju-solutions/bundle-canonical-kubernetes.git"
git clone ${BUNDLE_REPOSITORY} bundle

release-bundle() {
  LOCAL_PATH="$1"
  CS_PATH="$2"
  PUSH_CMD="charm push $LOCAL_PATH $CS_PATH"
  REVISION=`${PUSH_CMD} | tail -n +1 | head -1 | awk '{print $2}'`
  charm release --channel edge ${REVISION}
}

bundle/bundle -o ./bundles/cdk-flannel -c edge k8s/cdk cni/flannel
bundle/bundle -o ./bundles/core-flannel -c edge k8s/core cni/flannel
bundle/bundle -o ./bundles/cdk-flannel-elastic -c edge k8s/cdk cni/flannel monitor/elastic
bundle/bundle -o ./bundles/cdk-calico -c edge k8s/cdk cni/calico
bundle/bundle -o ./bundles/cdk-canal -c edge k8s/cdk cni/canal

release-bundle ./bundles/cdk-flannel cs:~containers/bundle/canonical-kubernetes
release-bundle ./bundles/core-flannel cs:~containers/bundle/kubernetes-core
release-bundle ./bundles/cdk-flannel-elastic cs:~containers/bundle/canonical-kubernetes-elastic
release-bundle ./bundles/cdk-calico cs:~containers/bundle/kubernetes-calico
release-bundle ./bundles/cdk-canal cs:~containers/bundle/canonical-kubernetes-canal

if [ "$RUN_TESTS" = "true" ]; then
  (cd integration-tests
    export TEST_CHARM_CHANNEL=edge
    pytest --no-print-logs --junit-xml=report.xml test_cdk.py
  )

  export FROM_CHANNEL=edge
  export TO_CHANNEL=beta
  ./charms/promote-all-charms-and-bundles.sh
fi
