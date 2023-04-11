# -*- mode:yaml; -*-
- charmed-kubernetes:
    fragments: 'k8s/cdk cni/calico cri/containerd'
    namespace: containers/bundle
    tags: 
        - k8s
        - charmed-kubernetes
        - bundle
- kubernetes-core:
    fragments: 'k8s/core cni/calico cri/containerd'
    namespace: containers/bundle
    tags:
        - k8s
        - kubernetes-core
        - bundle

- volcano:
    downstream: charmed-kubernetes/charm-volcano.git
    subdir: bundle
    fragments: ''
    tags: 
        - k8s-operator
        - bundle
        - volcano

##########################################################################
# Removed since it's built by github CI actions
# - kubeflow:
#     namespace: kubeflow-charmers
#     tags: ['general', 'kubeflow']

##########################################################################
# EOL CNI flavored bundles in favor for deploying with overlays
# - canonical-kubernetes:
#     fragments: 'k8s/cdk cni/flannel cri/containerd'
#     namespace: containers/bundle
#     tags: ['k8s', 'canonical-kubernetes']
# - kubernetes-calico:
#     fragments: 'k8s/cdk cni/calico cri/containerd'
#     namespace: containers/bundle
#     tags: ['k8s', 'kubernetes-calico']
# - canonical-kubernetes-canal:
#     fragments: 'k8s/cdk cni/canal cri/containerd'
#     namespace: containers/bundle
#     tags: ['k8s', 'canonical-kubernetes-canal']
# - kubernetes-tigera-secure-ee:
#     fragments: 'k8s/cdk cni/tigera-secure-ee cri/containerd'
#     namespace: containers/bundle
#     tags: ['k8s', 'kubernetes-tigera-secure-ee']

##########################################################################
# EOL in favor of metallb-speaker and metallb-controller operators
# - metallb:
#     namespace: containers
#     downstream: charmed-kubernetes/metallb-operator.git
#     skip-build: true
#     subdir: "bundle"
#    tags: ['k8s', 'addons', 'metallb']

##########################################################################
# EOL in favor of operator charm: https://charmhub.io/kubernetes-dashboard
# - kubernetes-dashboard-bundle:
#     namespace: containers
#     downstream: charmed-kubernetes/kubernetes-dashboard-operator.git
#     skip-build: true
#     subdir: "bundles"
#     tags: ['k8s', 'addons', 'kubernetes-dashboard-bundle']
#     branch: "main"
