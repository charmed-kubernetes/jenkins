# -*- mode:yaml; -*-
- canonical-kubernetes:
    fragments: 'k8s/cdk cni/flannel cri/containerd'
    namespace: containers/bundle
    tags: ['k8s', 'cdk-flannel']
- charmed-kubernetes:
    fragments: 'k8s/cdk cni/flannel cri/containerd'
    namespace: containers/bundle
    tags: ['k8s', 'charmed-flannel']
- kubernetes-core:
    fragments: 'k8s/core cni/flannel cri/containerd'
    namespace: containers/bundle
    tags: ['k8s', 'core-flannel']
- kubernetes-calico:
    fragments: 'k8s/cdk cni/calico cri/containerd'
    namespace: containers/bundle
    tags: ['k8s', 'cdk-calico']
- canonical-kubernetes-canal:
    fragments: 'k8s/cdk cni/canal cri/docker'
    namespace: containers/bundle
    tags: ['k8s', 'cdk-canal']
- kubernetes-tigera-secure-ee:
    fragments: 'k8s/cdk cni/tigera-secure-ee cri/containerd'
    namespace: containers/bundle
    tags: ['k8s', 'kubernetes-tigera-secure-ee']
- kubeflow:
    namespace: kubeflow-charmers
    tags: ['general', 'kubeflow']
