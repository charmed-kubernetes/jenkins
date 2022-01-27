# -*- mode:yaml; -*-
- test-kubernetes:
    fragments: 'k8s/core cni/flannel cri/containerd'
    namespace: containers/bundle
    tags: ['k8s', 'canonical-kubernetes']
