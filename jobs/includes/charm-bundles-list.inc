# -*- mode:yaml; -*-
- cdk-flannel:
    fragments: k8s/cdk cni/flannel
    charmstore: cs:~containers/bundle/canonical-kubernetes
    namespace: containers
- charmed-flannel:
    fragments: k8s/cdk cni/flannel
    charmstore: cs:~containers/bundle/charmed-kubernetes
    namespace: containers
- core-flannel:
    fragments: k8s/core cni/flannel
    charmstore: cs:~containers/bundle/kubernetes-core
    namespace: containers
- cdk-calico:
    fragments: k8s/cdk cni/calico
    charmstore: cs:~containers/bundle/kubernetes-calico
    namespace: containers
- cdk-canal:
    fragments: k8s/cdk cni/canal
    charmstore: cs:~containers/bundle/canonical-kubernetes-canal
    namespace: containers
- kubernetes-tigera-secure-ee:
    fragments: k8s/cdk cni/tigera-secure-ee
    charmstore: cs:~containers/bundle/kubernetes-tigera-secure-ee
    namespace: containers
- kubeflow:
    charmstore: cs:~kubeflow-charmers/kubeflow
    namespace: kubeflow-charmers
