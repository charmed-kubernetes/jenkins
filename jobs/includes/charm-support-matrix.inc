# -*- mode:yaml; -*-
- calico:
    upstream: "https://github.com/charmed-kubernetes/layer-calico.git"
    downstream: 'charmed-kubernetes/layer-calico.git'
    resource_build_sh: 'build-calico-resource.sh'
    namespace: 'containers'
    tags: ['k8s', 'calico']
- canal:
    upstream: "https://github.com/charmed-kubernetes/layer-canal.git"
    downstream: 'charmed-kubernetes/layer-canal.git'
    resource_build_sh: 'build-canal-resources.sh'
    namespace: 'containers'
    tags: ['k8s', 'canal']
- containerd:
    upstream: "https://github.com/charmed-kubernetes/charm-containerd.git"
    downstream: 'charmed-kubernetes/charm-containerd.git'
    namespace: 'containers'
    tags: ['k8s', 'containerd']
- docker:
    upstream: "https://github.com/charmed-kubernetes/charm-docker.git"
    downstream: 'charmed-kubernetes/charm-docker.git'
    namespace: 'containers'
    tags: ['k8s', 'docker']
- easyrsa:
    upstream: "https://github.com/charmed-kubernetes/layer-easyrsa.git"
    downstream: 'charmed-kubernetes/layer-easyrsa.git'
    namespace: 'containers'
    tags: ['k8s', 'easyrsa']
- etcd:
    upstream: "https://github.com/charmed-kubernetes/layer-etcd.git"
    downstream: 'charmed-kubernetes/layer-etcd.git'
    namespace: 'containers'
    tags: ['k8s', 'etcd']
- flannel:
    upstream: "https://github.com/charmed-kubernetes/charm-flannel.git"
    downstream: 'charmed-kubernetes/charm-flannel.git'
    resource_build_sh: 'build-flannel-resources.sh'
    namespace: 'containers'
    tags: ['k8s', 'flannel']
- kata:
    upstream: "https://github.com/charmed-kubernetes/charm-kata.git"
    downstream: 'charmed-kubernetes/charm-kata.git'
    namespace: 'containers'
    tags: ['k8s', 'containerd']
- kubeapi-load-balancer:
    upstream: "https://github.com/charmed-kubernetes/charm-kubeapi-load-balancer.git"
    downstream: 'charmed-kubernetes/charm-kubeapi-load-balancer.git'
    namespace: 'containers'
    tags: ['k8s', 'kubeapi-load-balancer']
- kubernetes-e2e:
    upstream: "https://github.com/charmed-kubernetes/charm-kubernetes-e2e.git"
    downstream: 'charmed-kubernetes/charm-kubernetes-e2e.git'
    namespace: 'containers'
    tags: ['k8s', 'kubernetes-e2e']
- kubernetes-master:
    upstream: "https://github.com/charmed-kubernetes/charm-kubernetes-master.git"
    downstream: 'charmed-kubernetes/charm-kubernetes-master.git'
    namespace: 'containers'
    tags: ['k8s', 'kubernetes-master']
- kubernetes-worker:
    upstream: "https://github.com/charmed-kubernetes/charm-kubernetes-worker.git"
    downstream: 'charmed-kubernetes/charm-kubernetes-worker.git'
    resource_build_sh: 'build-cni-resources.sh'
    namespace: 'containers'
    tags: ['k8s', 'kubernetes-worker']
- tigera-secure-ee:
    upstream: "https://github.com/charmed-kubernetes/layer-tigera-secure-ee.git"
    downstream: 'charmed-kubernetes/layer-tigera-secure-ee.git'
    resource_build_sh: 'build-resources.sh'
    namespace: 'containers'
    tags: ['k8s', 'tigera-secure-ee']
- keepalived:
    upstream: "https://github.com/juju-solutions/charm-keepalived.git"
    downstream: 'juju-solutions/charm-keepalived.git'
    namespace: 'containers'
    tags: ['general', 'keepalived']
- docker-registry:
    upstream: "https://github.com/CanonicalLtd/docker-registry-charm.git"
    downstream: 'charmed-kubernetes/docker-registry-charm.git'
    namespace: 'containers'
    tags: ['general', 'docker-registry', 'k8s']
- aws-iam:
    upstream: "https://github.com/charmed-kubernetes/charm-aws-iam.git"
    namespace: 'containers'
    downstream: 'charmed-kubernetes/charm-aws-iam'
    tags: ['k8s', 'aws-iam']
- azure-integrator:
    upstream: "https://github.com/juju-solutions/charm-azure-integrator.git"
    namespace: 'containers'
    downstream: 'charmed-kubernetes/charm-azure-integrator'
    tags: ['k8s', 'charm-azure-integrator']
- gcp-integrator:
    upstream: "https://github.com/juju-solutions/charm-gcp-integrator.git"
    namespace: 'containers'
    downstream: 'charmed-kubernetes/charm-gcp-integrator'
    tags: ['k8s', 'charm-gcp-integrator']
- aws-integrator:
    upstream: "https://github.com/juju-solutions/charm-aws-integrator.git"
    namespace: 'containers'
    downstream: 'charmed-kubernetes/charm-aws-integrator'
    tags: ['k8s', 'charm-aws-integrator']
- openstack-integrator:
    upstream: "https://github.com/juju-solutions/charm-openstack-integrator.git"
    namespace: 'containers'
    downstream: 'charmed-kubernetes/charm-openstack-integrator'
    tags: ['k8s', 'charm-openstack-integrator']
- vsphere-integrator:
    upstream: "https://github.com/juju-solutions/charm-vsphere-integrator.git"
    namespace: 'containers'
    downstream: 'charmed-kubernetes/charm-vsphere-integrator'
    tags: ['k8s', 'charm-vsphere-integrator']
# - multus:
#     upstream: "https://github.com/charmed-kubernetes/charm-multus.git"
#     namespace: 'containers'
#     downstream: 'charmed-kubernetes/charm-multus'
#     tags: ['k8s', 'charm-multus']
#     override-build: |
#       git submodule init
#       git submodule update

# - nfs:
#     upstream: "https://github.com/hyperbolic2346/nfs-charm.git"
#     namespace: 'containers'
#     downstream: 'charmed-kubernetes/nfs-charm'
#     tags: ['k8s', 'nfs']
