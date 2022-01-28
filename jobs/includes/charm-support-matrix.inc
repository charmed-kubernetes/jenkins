# -*- mode:yaml; -*-
- calico:
    upstream: "https://github.com/charmed-kubernetes/layer-calico.git"
    downstream: 'charmed-kubernetes/layer-calico.git'
    build-resources: "cd {out_path}; bash {src_path}/build-calico-resource.sh"
    namespace: 'containers'
    tags: ['k8s', 'calico']
- canal:
    upstream: "https://github.com/charmed-kubernetes/layer-canal.git"
    downstream: 'charmed-kubernetes/layer-canal.git'
    build-resources: "cd {out_path}; bash {src_path}/build-canal-resources.sh"
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
    build-resources: "cd {out_path}; bash {src_path}/build-flannel-resources.sh"
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
- kubernetes-control-plane:
    upstream: "https://github.com/charmed-kubernetes/charm-kubernetes-control-plane.git"
    downstream: 'charmed-kubernetes/charm-kubernetes-control-plane.git'
    build-resources: "cd {out_path}; bash {src_path}/build-cni-resources.sh"
    namespace: 'containers'
    tags: ['k8s', 'kubernetes-control-plane']
    store: 'ch'
- kubernetes-worker:
    upstream: "https://github.com/charmed-kubernetes/charm-kubernetes-worker.git"
    downstream: 'charmed-kubernetes/charm-kubernetes-worker.git'
    build-resources: "cd {out_path}; bash {src_path}/build-cni-resources.sh"
    namespace: 'containers'
    tags: ['k8s', 'kubernetes-worker']
- tigera-secure-ee:
    upstream: "https://github.com/charmed-kubernetes/layer-tigera-secure-ee.git"
    downstream: 'charmed-kubernetes/layer-tigera-secure-ee.git'
    build-resources: "cd {out_path}; bash {src_path}/build-resources.sh"
    namespace: 'containers'
    tags: ['k8s', 'tigera-secure-ee']
- keepalived:
    upstream: "https://github.com/charmed-kubernetes/charm-keepalived.git"
    downstream: 'charmed-kubernetes/charm-keepalived.git'
    namespace: 'containers'
    tags: ['general', 'keepalived', 'k8s']
    subdir: "src"
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
- metallb-controller:
    upstream: "https://github.com/charmed-kubernetes/metallb-operator.git"
    subdir: "charms/metallb-controller"
    namespace: "containers"
    downstream: "charmed-kubernetes/metallb-operator"
    tags: ["k8s", "metallb", "metallb-controller"]
- metallb-speaker:
    upstream: "https://github.com/charmed-kubernetes/metallb-operator.git"
    subdir: "charms/metallb-speaker"
    namespace: "containers"
    downstream: "charmed-kubernetes/metallb-operator"
    tags: ["k8s", "metallb", "metallb-speaker"]
- multus:
    upstream: "https://github.com/charmed-kubernetes/charm-multus.git"
    namespace: "containers"
    downstream: "charmed-kubernetes/charm-multus"
    tags: ["k8s", "multus"]
    build-resources: "cd {src_path}/net-attach-def-manager; ./build"
- sriov-cni:
    upstream: "https://github.com/charmed-kubernetes/charm-sriov-cni.git"
    namespace: "containers"
    downstream: "charmed-kubernetes/charm-sriov-cni"
    tags: ["k8s", "sriov", "sriov-cni"]
    build-resources: "cd {src_path}/image; ./build"
- sriov-network-device-plugin:
    upstream: "https://github.com/charmed-kubernetes/charm-sriov-network-device-plugin.git"
    namespace: "containers"
    downstream: "charmed-kubernetes/charm-sriov-network-device-plugin"
    tags: ["k8s", "sriov", "sriov-network-device-plugin"]
- coredns:
    upstream: "https://github.com/charmed-kubernetes/charm-coredns.git"
    namespace: "containers"
    downstream: "charmed-kubernetes/charm-coredns"
    tags: ["k8s", "coredns"]
- k8s-dashboard:
    upstream: "https://github.com/charmed-kubernetes/kubernetes-dashboard-operator"
    subdir: "charms/kubernetes-dashboard"
    namespace: "containers"
    downstream: "charmed-kubernetes/kubernetes-dashboard-operator"
    tags: ["k8s", "k8s-dashboard"]
    branch: "main"
- dashboard-metrics-scraper:
    upstream: "https://github.com/charmed-kubernetes/kubernetes-dashboard-operator"
    subdir: "charms/dashboard-metrics-scraper"
    namespace: "containers"
    downstream: "charmed-kubernetes/kubernetes-dashboard-operator"
    tags: ["k8s", "dashboard-metrics-scraper"]
    branch: "main"

# - nfs:
#     upstream: "https://github.com/hyperbolic2346/nfs-charm.git"
#     namespace: 'containers'
#     downstream: 'charmed-kubernetes/nfs-charm'
#     tags: ['k8s', 'nfs']
