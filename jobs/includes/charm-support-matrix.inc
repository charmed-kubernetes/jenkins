# -*- mode:yaml; -*-
- calico:
    summary: "A robust Software Defined Network from Project Calico"
    bugs: 'https://bugs.launchpad.net/charmed-kubernetes'
    store: https://charmhub.io/calico
    docs: https://charmhub.io/calico/docs
    upstream: "https://github.com/charmed-kubernetes/layer-calico.git"
    downstream: 'charmed-kubernetes/layer-calico.git'
    build-resources: "cd {out_path}; bash {src_path}/build-calico-resource.sh"
    tags: ['k8s', 'calico', 'core', 'cni']
- canal:
    summary: "A Software Defined Network based on Flannel and Calico"
    bugs: 'https://bugs.launchpad.net/charmed-kubernetes'
    store: https://charmhub.io/canal
    docs: https://charmhub.io/canal/docs
    upstream: "https://github.com/charmed-kubernetes/layer-canal.git"
    downstream: 'charmed-kubernetes/layer-canal.git'
    build-resources: "cd {out_path}; bash {src_path}/build-canal-resources.sh"
    tags: ['k8s', 'canal', 'cni']
- containerd:
    summary: "Containerd container runtime subordinate"
    bugs: 'https://bugs.launchpad.net/charmed-kubernetes'
    store: https://charmhub.io/containerd
    docs: https://charmhub.io/containerd/docs
    upstream: "https://github.com/charmed-kubernetes/charm-containerd.git"
    downstream: 'charmed-kubernetes/charm-containerd.git'
    tags: ['k8s', 'containerd', 'core', 'cri']
- docker:
    upstream: "https://github.com/charmed-kubernetes/charm-docker.git"
    downstream: 'charmed-kubernetes/charm-docker.git'
    tags: ['k8s', 'docker']
    store: 'ch'
- easyrsa:
    summary: "Deploys and manages EasyRSA to create a Certificate Authority (CA)"
    bugs: 'https://bugs.launchpad.net/charmed-kubernetes'
    store: 'https://charmhub.io/easyrsa'
    docs: 'https://charmhub.io/easyrsa/docs'
    upstream: "https://github.com/charmed-kubernetes/layer-easyrsa.git"
    downstream: 'charmed-kubernetes/layer-easyrsa.git'
    tags: ['k8s', 'easyrsa', 'core']
- etcd:
    summary: "Deploy a TLS terminated ETCD Cluster"
    bugs: 'https://bugs.launchpad.net/charmed-kubernetes'
    store: 'https://charmhub.io/etcd'
    docs: 'https://charmhub.io/etcd/docs'
    upstream: "https://github.com/charmed-kubernetes/layer-etcd.git"
    downstream: 'charmed-kubernetes/layer-etcd.git'
    tags: ['k8s', 'etcd', 'core']
- flannel:
    summary: "A charm that provides a robust Software Defined Network"
    bugs: 'https://bugs.launchpad.net/charmed-kubernetes'
    store: 'https://charmhub.io/flannel'
    docs: 'https://charmhub.io/flannel/docs'
    upstream: "https://github.com/charmed-kubernetes/charm-flannel.git"
    downstream: 'charmed-kubernetes/charm-flannel.git'
    build-resources: "cd {out_path}; bash {src_path}/build-flannel-resources.sh"
    tags: ['k8s', 'flannel', 'cni']
- kata:
    summary: "Kata untrusted container runtime subordinate"
    bugs: 'https://bugs.launchpad.net/charmed-kubernetes'
    store: 'https://charmhub.io/kata'
    docs: 'https://charmhub.io/kata/docs'
    upstream: "https://github.com/charmed-kubernetes/charm-kata.git"
    downstream: 'charmed-kubernetes/charm-kata.git'
    tags: ['k8s', 'kata', 'core']
- kubeapi-load-balancer:
    summary: "Nginx Load Balancer"
    bugs: 'https://bugs.launchpad.net/charmed-kubernetes'
    store: 'https://charmhub.io/kubeapi-load-balancer'
    docs: 'https://charmhub.io/kubeapi-load-balancer/docs'
    upstream: "https://github.com/charmed-kubernetes/charm-kubeapi-load-balancer.git"
    downstream: 'charmed-kubernetes/charm-kubeapi-load-balancer.git'
    tags: ['k8s', 'kubeapi-load-balancer', 'core']
- kube-state-metrics:
    summary: "a service that listens to the Kubernetes API and generates metrics"
    bugs: 'https://bugs.launchpad.net/charmed-kubernetes'
    store: 'https://charmhub.io/kube-state-metrics'
    docs: 'https://charmhub.io/kube-state-metrics/docs'
    upstream: "https://github.com/charmed-kubernetes/kube-state-metrics-operator.git"
    downstream: 'charmed-kubernetes/kube-state-metrics-operator.git'
    tags: ['k8s-operator', 'kube-state-metrics']
- kubernetes-autoscaler:
    summary: "automatically scales up and down a kubernetes cluster"
    bugs: 'https://bugs.launchpad.net/charmed-kubernetes'
    store: 'https://charmhub.io/kubernetes-autoscaler'
    docs: 'https://charmhub.io/kubernetes-autoscaler/docs'
    upstream: "https://github.com/charmed-kubernetes/charm-kubernetes-autoscaler.git"
    downstream: 'charmed-kubernetes/charm-kubernetes-autoscaler.git'
    tags: ['k8s-operator', 'kubernetes-autoscaler']
- kubernetes-e2e:
    summary: "End-to-end (e2e) tests for Kubernetes"
    bugs: 'https://bugs.launchpad.net/charmed-kubernetes'
    store: 'https://charmhub.io/kubernetes-e2e'
    docs: 'https://charmhub.io/kubernetes-e2e/docs'
    upstream: "https://github.com/charmed-kubernetes/charm-kubernetes-e2e.git"
    downstream: 'charmed-kubernetes/charm-kubernetes-e2e.git'
    tags: ['k8s', 'kubernetes-e2e']
- kubernetes-control-plane:
    summary: "The Kubernetes control plane"
    bugs: 'https://bugs.launchpad.net/charmed-kubernetes'
    store: 'https://charmhub.io/kubernetes-control-plane'
    docs: 'https://charmhub.io/kubernetes-control-plane/docs'
    upstream: "https://github.com/charmed-kubernetes/charm-kubernetes-control-plane.git"
    downstream: 'charmed-kubernetes/charm-kubernetes-control-plane.git'
    build-resources: "cd {out_path}; bash {src_path}/build-cni-resources.sh"
    tags: ['k8s', 'kubernetes-control-plane', 'core']
- kubernetes-metrics-server:
    summary: "Exposes core Kubernetes metrics via metrics API "
    bugs: 'https://bugs.launchpad.net/charmed-kubernetes'
    store: 'https://charmhub.io/kubernetes-metrics-server'
    docs: 'https://charmhub.io/kubernetes-metrics-server/docs'
    upstream: "https://github.com/charmed-kubernetes/kubernetes-metrics-server-operator.git"
    downstream: 'charmed-kubernetes/kubernetes-metrics-server-operator.git'
    tags: ['k8s-operator', 'kubernetes-metrics-server']
- kubernetes-worker:
    summary: "The workload bearing units of a kubernetes cluster"
    bugs: 'https://bugs.launchpad.net/charmed-kubernetes'
    store: 'https://charmhub.io/kubernetes-worker'
    docs: 'https://charmhub.io/kubernetes-worker/docs'
    upstream: "https://github.com/charmed-kubernetes/charm-kubernetes-worker.git"
    downstream: 'charmed-kubernetes/charm-kubernetes-worker.git'
    build-resources: "cd {out_path}; bash {src_path}/build-cni-resources.sh"
    tags: ['k8s', 'kubernetes-worker', 'core']
- tigera-secure-ee:
    summary: "Tigera Secure Enterprise Edition"
    bugs: 'https://bugs.launchpad.net/charmed-kubernetes'
    store: 'https://charmhub.io/tigera-secure-ee'
    docs: 'https://charmhub.io/tigera-secure-ee/docs'
    upstream: "https://github.com/charmed-kubernetes/layer-tigera-secure-ee.git"
    downstream: 'charmed-kubernetes/layer-tigera-secure-ee.git'
    build-resources: "cd {out_path}; bash {src_path}/build-resources.sh"
    tags: ['k8s', 'tigera-secure-ee', 'cni']
- keepalived:
    summary: "Failover and monitoring daemon for LVS clusters"
    bugs: 'https://bugs.launchpad.net/charmed-kubernetes'
    store: 'https://charmhub.io/keepalived'
    docs: 'https://charmhub.io/keepalived/docs'
    upstream: "https://github.com/charmed-kubernetes/charm-keepalived.git"
    downstream: 'charmed-kubernetes/charm-keepalived.git'
    tags: ['general', 'keepalived', 'k8s']
    subdir: "src"
- docker-registry:
    summary: "Registry for docker images"
    bugs: 'https://bugs.launchpad.net/charmed-kubernetes'
    store: 'https://charmhub.io/docker-registry'
    docs: 'https://charmhub.io/docker-registry/docs'
    upstream: "https://github.com/CanonicalLtd/docker-registry-charm.git"
    downstream: 'charmed-kubernetes/docker-registry-charm.git'
    tags: ['general', 'docker-registry', 'k8s']
- aws-iam:
    summary: ""
    bugs: 'https://bugs.launchpad.net/charmed-kubernetes'
    store: 'https://charmhub.io/aws-iam'
    docs: 'https://charmhub.io/aws-iam/docs'
    upstream: "https://github.com/charmed-kubernetes/charm-aws-iam.git"
    downstream: 'charmed-kubernetes/charm-aws-iam'
    tags: ['k8s', 'aws-iam']
- azure-integrator:
    summary: ""
    bugs: 'https://bugs.launchpad.net/charmed-kubernetes'
    store: 'https://charmhub.io/azure-integrator'
    docs: 'https://charmhub.io/azure-integrator/docs'
    upstream: "https://github.com/juju-solutions/charm-azure-integrator.git"
    downstream: 'charmed-kubernetes/charm-azure-integrator'
    tags: ['k8s', 'charm-azure-integrator', 'integrator']
- gcp-integrator:
    summary: "Charm which enables Google GCP integrations for Juju"
    bugs: 'https://bugs.launchpad.net/charmed-kubernetes'
    store: 'https://charmhub.io/gcp-integrator'
    docs: 'https://charmhub.io/gcp-integrator/docs'
    upstream: "https://github.com/juju-solutions/charm-gcp-integrator.git"
    downstream: 'charmed-kubernetes/charm-gcp-integrator'
    tags: ['k8s', 'charm-gcp-integrator', 'integrator']
- github-runner:
    upstream: https://github.com/charmed-kubernetes/github-runner-operator.git
    downstream: 'charmed-kubernetes/github-runner-operator'
    tags: ['github-runner']
- aws-integrator:
    summary: "Charm to enable AWS integrations via Juju relations."
    bugs: 'https://bugs.launchpad.net/charmed-kubernetes'
    store: 'https://charmhub.io/aws-integrator'
    docs: 'https://charmhub.io/aws-integrator/docs'
    upstream: "https://github.com/juju-solutions/charm-aws-integrator.git"
    downstream: 'charmed-kubernetes/charm-aws-integrator'
    tags: ['k8s', 'charm-aws-integrator', 'integrator']
- openstack-integrator:
    summary: "Charm which enables OpenStack integrations for Juju"
    bugs: 'https://bugs.launchpad.net/charmed-kubernetes'
    store: 'https://charmhub.io/openstack-integrator'
    docs: 'https://charmhub.io/openstack-integrator/docs'
    upstream: "https://github.com/juju-solutions/charm-openstack-integrator.git"
    downstream: 'charmed-kubernetes/charm-openstack-integrator'
    tags: ['k8s', 'charm-openstack-integrator', 'integrator']
- vsphere-integrator:
    summary: "Charm which enables vSphere integrations for Juju"
    bugs: 'https://bugs.launchpad.net/charmed-kubernetes'
    store: 'https://charmhub.io/vsphere-integrator'
    docs: 'https://charmhub.io/vsphere-integrator/docs'
    upstream: "https://github.com/juju-solutions/charm-vsphere-integrator.git"
    downstream: 'charmed-kubernetes/charm-vsphere-integrator'
    tags: ['k8s', 'charm-vsphere-integrator', 'integrator']
- metallb-controller:
    summary: "Controller charm for the metallb loadbalancer"
    bugs: 'https://bugs.launchpad.net/charmed-kubernetes'
    store: 'https://charmhub.io/metallb-controller'
    docs: 'https://charmhub.io/metallb-controller/docs'
    upstream: "https://github.com/charmed-kubernetes/metallb-operator.git"
    subdir: "charms/metallb-controller"
    downstream: "charmed-kubernetes/metallb-operator"
    tags: ["k8s", "metallb", "metallb-controller"]
- metallb-speaker:
    summary: "Speaker charm for the metallb loadbalancer"
    bugs: 'https://bugs.launchpad.net/charmed-kubernetes'
    store: 'https://charmhub.io/metallb-speaker'
    docs: 'https://charmhub.io/metallb-speaker/docs'
    upstream: "https://github.com/charmed-kubernetes/metallb-operator.git"
    subdir: "charms/metallb-speaker"
    downstream: "charmed-kubernetes/metallb-operator"
    tags: ["k8s", "metallb", "metallb-speaker"]
- multus:
    summary: "a CNI plugin for attaching multiple network interfaces"
    bugs: 'https://bugs.launchpad.net/charmed-kubernetes'
    store: 'https://charmhub.io/multus'
    docs: 'https://charmhub.io/multus/docs'
    upstream: "https://github.com/charmed-kubernetes/charm-multus.git"
    downstream: "charmed-kubernetes/charm-multus"
    tags: ["k8s", "multus", "cni"]
    build-resources: "cd {src_path}/net-attach-def-manager; ./build"
- sriov-cni:
    summary: "Attach SR-IOV Virtual Functions (VFs) directly to pods"
    bugs: 'https://bugs.launchpad.net/charmed-kubernetes'
    store: 'https://charmhub.io/sriov-cni'
    docs: 'https://charmhub.io/sriov-cni/docs'
    upstream: "https://github.com/charmed-kubernetes/charm-sriov-cni.git"
    downstream: "charmed-kubernetes/charm-sriov-cni"
    tags: ["k8s", "sriov", "sriov-cni", "cni"]
    build-resources: "cd {src_path}/image; ./build"
- sriov-network-device-plugin:
    summary: "Enable SR-IOV support"
    bugs: 'https://bugs.launchpad.net/charmed-kubernetes'
    store: 'https://charmhub.io/sriov-network-device-plugin'
    docs: 'https://charmhub.io/sriov-network-device-plugin/docs'
    upstream: "https://github.com/charmed-kubernetes/charm-sriov-network-device-plugin.git"
    downstream: "charmed-kubernetes/charm-sriov-network-device-plugin"
    tags: ["k8s", "sriov", "sriov-network-device-plugin", "cni"]
- coredns:
    summary: "The CoreDNS domain name service provider"
    bugs: 'https://bugs.launchpad.net/charmed-kubernetes'
    store: 'https://charmhub.io/coredns'
    docs: 'https://charmhub.io/coredns/docs'
    upstream: "https://github.com/charmed-kubernetes/charm-coredns.git"
    downstream: "charmed-kubernetes/charm-coredns"
    tags: ["k8s", "coredns", "cni"]

# EOL in favor of operator charm: https://charmhub.io/kubernetes-dashboard
# - k8s-dashboard:
#     upstream: "https://github.com/charmed-kubernetes/kubernetes-dashboard-operator"
#     subdir: "charms/kubernetes-dashboard"
#     namespace: "containers"
#     downstream: "charmed-kubernetes/kubernetes-dashboard-operator"
#     tags: ["k8s", "k8s-dashboard"]
#     branch: "main"
# - dashboard-metrics-scraper:
#     upstream: "https://github.com/charmed-kubernetes/kubernetes-dashboard-operator"
#     subdir: "charms/dashboard-metrics-scraper"
#     namespace: "containers"
#     downstream: "charmed-kubernetes/kubernetes-dashboard-operator"
#     tags: ["k8s", "dashboard-metrics-scraper"]
#     branch: "main"

# - nfs:
#     upstream: "https://github.com/hyperbolic2346/nfs-charm.git"
#     namespace: 'containers'
#     downstream: 'charmed-kubernetes/nfs-charm'
#     tags: ['k8s', 'nfs']
