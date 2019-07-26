# -*- mode:yaml; -*-
- canonical-kubernetes:
    fragments: 'k8s/cdk cni/flannel cri/containerd'
    namespace: containers/bundle
    tags: ['k8s', 'canonical-kubernetes']
- charmed-kubernetes:
    fragments: 'k8s/cdk cni/flannel cri/containerd'
    namespace: containers/bundle
    tags: ['k8s', 'charmed-kubernetes']
- kubernetes-core:
    fragments: 'k8s/core cni/flannel cri/containerd'
    namespace: containers/bundle
    tags: ['k8s', 'kubernetes-core']
- kubernetes-calico:
    fragments: 'k8s/cdk cni/calico cri/containerd'
    namespace: containers/bundle
    tags: ['k8s', 'kubernetes-calico']
- canonical-kubernetes-canal:
    fragments: 'k8s/cdk cni/canal cri/containerd'
    namespace: containers/bundle
    tags: ['k8s', 'canonical-kubernetes-canal']
- kubernetes-tigera-secure-ee:
    fragments: 'k8s/cdk cni/tigera-secure-ee cri/containerd'
    namespace: containers/bundle
    tags: ['k8s', 'kubernetes-tigera-secure-ee']
- kubeflow:
    namespace: kubeflow-charmers
    tags: ['general', 'kubeflow']
