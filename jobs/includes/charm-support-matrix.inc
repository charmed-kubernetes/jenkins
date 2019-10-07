# -*- mode:yaml; -*-
- calico:
    downstream: 'charmed-kubernetes/layer-calico.git'
    resource_build_sh: 'build-calico-resource.sh'
    namespace: 'containers'
    tags: ['k8s', 'calico']
- canal:
    downstream: 'charmed-kubernetes/layer-canal.git'
    resource_build_sh: 'build-canal-resources.sh'
    namespace: 'containers'
    tags: ['k8s', 'canal']
- containerd:
    downstream: 'charmed-kubernetes/charm-containerd.git'
    namespace: 'containers'
    tags: ['k8s', 'containerd']
- docker:
    downstream: 'charmed-kubernetes/charm-docker.git'
    namespace: 'containers'
    tags: ['k8s', 'docker']
- easyrsa:
    downstream: 'charmed-kubernetes/layer-easyrsa.git'
    namespace: 'containers'
    tags: ['k8s', 'easyrsa']
- etcd:
    downstream: 'charmed-kubernetes/layer-etcd.git'
    namespace: 'containers'
    tags: ['k8s', 'etcd']
- flannel:
    downstream: 'charmed-kubernetes/charm-flannel.git'
    resource_build_sh: 'build-flannel-resources.sh'
    namespace: 'containers'
    tags: ['k8s', 'flannel']
- kata:
    downstream: 'charmed-kubernetes/charm-kata.git'
    namespace: 'containers'
    tags: ['k8s', 'containerd']
- kubeapi-load-balancer:
    downstream: 'charmed-kubernetes/charm-kubeapi-load-balancer.git'
    namespace: 'containers'
    tags: ['k8s', 'kubeapi-load-balancer']
- kubernetes-e2e:
    downstream: 'charmed-kubernetes/charm-kubernetes-e2e.git'
    namespace: 'containers'
    tags: ['k8s', 'kubernetes-e2e']
- kubernetes-master:
    downstream: 'charmed-kubernetes/charm-kubernetes-master.git'
    namespace: 'containers'
    tags: ['k8s', 'kubernetes-master']
- kubernetes-worker:
    downstream: 'charmed-kubernetes/charm-kubernetes-worker.git'
    resource_build_sh: 'build-cni-resources.sh'
    namespace: 'containers'
    tags: ['k8s', 'kubernetes-worker']
- tigera-secure-ee:
    downstream: 'charmed-kubernetes/layer-tigera-secure-ee.git'
    resource_build_sh: 'build-resources.sh'
    namespace: 'containers'
    tags: ['k8s', 'tigera-secure-ee']
- keepalived:
    downstream: 'juju-solutions/charm-keepalived.git'
    namespace: 'containers'
    tags: ['general', 'keepalived']
- docker-registry:
    downstream: 'CanonicalLtd/docker-registry-charm.git'
    namespace: 'containers'
    tags: ['general', 'docker-registry']
- aws-iam:
    namespace: 'containers'
    downstream: 'charmed-kubernetes/charm-aws-iam'
    tags: ['k8s', 'aws-iam']
- charm-azure-integrator:
    namespace: 'containers'
    downstream: 'charmed-kubernetes/charm-azure-integrator'
    tags: ['k8s', 'charm-azure-integrator']
- charm-gcp-integrator:
    namespace: 'containers'
    downstream: 'charmed-kubernetes/charm-gcp-integrator'
    tags: ['k8s', 'charm-gcp-integrator']
- charm-aws-integrator:
    namespace: 'containers'
    downstream: 'charmed-kubernetes/charm-aws-integrator'
    tags: ['k8s', 'charm-aws-integrator']
- charm-openstack-integrator:
    namespace: 'containers'
    downstream: 'charmed-kubernetes/charm-openstack-integrator'
    tags: ['k8s', 'charm-openstack-integrator']
- charm-vsphere-integrator:
    namespace: 'containers'
    downstream: 'charmed-kubernetes/charm-vsphere-integrator'
    tags: ['k8s', 'charm-vsphere-integrator']
