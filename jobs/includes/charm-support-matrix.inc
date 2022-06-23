# -*- mode:yaml; -*-
- calico:
    bugs: 'https://bugs.launchpad.net/charm-calico'
    build-resources: 'cd {out_path}; bash {src_path}/build-calico-resource.sh'
    docs: 'https://charmhub.io/calico/docs'
    downstream: charmed-kubernetes/layer-calico.git
    store: 'https://charmhub.io/calico'
    summary: A robust Software Defined Network from Project Calico
    tags:
      - k8s
      - calico
      - core
      - cni
    upstream: 'https://github.com/charmed-kubernetes/layer-calico.git'
- canal:
    bugs: 'https://bugs.launchpad.net/charm-canal'
    build-resources: 'cd {out_path}; bash {src_path}/build-canal-resources.sh'
    docs: 'https://charmhub.io/canal/docs'
    downstream: charmed-kubernetes/layer-canal.git
    store: 'https://charmhub.io/canal'
    summary: A Software Defined Network based on Flannel and Calico
    tags:
      - k8s
      - canal
      - cni
    upstream: 'https://github.com/charmed-kubernetes/layer-canal.git'
- containerd:
    bugs: 'https://bugs.launchpad.net/charm-containerd'
    docs: 'https://charmhub.io/containerd/docs'
    downstream: charmed-kubernetes/charm-containerd.git
    store: 'https://charmhub.io/containerd'
    summary: Containerd container runtime subordinate
    tags:
      - k8s
      - containerd
      - core
      - cri
    upstream: 'https://github.com/charmed-kubernetes/charm-containerd.git'
- easyrsa:
    bugs: 'https://bugs.launchpad.net/charm-easyrsa'
    docs: 'https://charmhub.io/easyrsa/docs'
    downstream: charmed-kubernetes/layer-easyrsa.git
    store: 'https://charmhub.io/easyrsa'
    summary: Deploys and manages EasyRSA to create a Certificate Authority (CA)
    tags:
      - k8s
      - easyrsa
      - core
    upstream: 'https://github.com/charmed-kubernetes/layer-easyrsa.git'
- etcd:
    bugs: 'https://bugs.launchpad.net/charm-etcd'
    docs: 'https://charmhub.io/etcd/docs'
    downstream: charmed-kubernetes/layer-etcd.git
    store: 'https://charmhub.io/etcd'
    summary: Deploy a TLS terminated ETCD Cluster
    tags:
      - k8s
      - etcd
      - core
    upstream: 'https://github.com/charmed-kubernetes/layer-etcd.git'
- flannel:
    bugs: 'https://bugs.launchpad.net/charm-flannel'
    build-resources: 'cd {out_path}; bash {src_path}/build-flannel-resources.sh'
    docs: 'https://charmhub.io/flannel/docs'
    downstream: charmed-kubernetes/charm-flannel.git
    store: 'https://charmhub.io/flannel'
    summary: A charm that provides a robust Software Defined Network
    tags:
      - k8s
      - flannel
      - cni
    upstream: 'https://github.com/charmed-kubernetes/charm-flannel.git'
- kata:
    bugs: 'https://bugs.launchpad.net/charm-kata'
    docs: 'https://charmhub.io/kata/docs'
    downstream: charmed-kubernetes/charm-kata.git
    store: 'https://charmhub.io/kata'
    summary: Kata untrusted container runtime subordinate
    tags:
      - k8s
      - kata
      - core
    upstream: 'https://github.com/charmed-kubernetes/charm-kata.git'
- kube-ovn:
    bugs: 'https://bugs.launchpad.net/charm-kube-ovn'
    docs: 'https://charmhub.io/kube-ovn/docs'
    downstream: charmed-kubernetes/charm-kube-ovn.git
    store: 'https://charmhub.io/kube-ovn'
    summary: A Software Defined Network based on Kube-OVN
    tags:
      - k8s
      - kube-ovn
      - cni
    upstream: 'https://github.com/charmed-kubernetes/charm-kube-ovn.git'
- kubeapi-load-balancer:
    bugs: 'https://bugs.launchpad.net/charm-kubeapi-load-balancer'
    docs: 'https://charmhub.io/kubeapi-load-balancer/docs'
    downstream: charmed-kubernetes/charm-kubeapi-load-balancer.git
    store: 'https://charmhub.io/kubeapi-load-balancer'
    summary: Nginx Load Balancer
    tags:
      - k8s
      - kubeapi-load-balancer
      - core
    upstream: 'https://github.com/charmed-kubernetes/charm-kubeapi-load-balancer.git'
- kube-state-metrics:
    bugs: 'https://bugs.launchpad.net/charmed-kubernetes'
    docs: 'https://charmhub.io/kube-state-metrics/docs'
    downstream: charmed-kubernetes/kube-state-metrics-operator.git
    store: 'https://charmhub.io/kube-state-metrics'
    summary: a service that listens to the Kubernetes API and generates metrics
    tags:
      - k8s-operator
      - kube-state-metrics
      - docs-extra
    upstream: 'https://github.com/charmed-kubernetes/kube-state-metrics-operator.git'
- kubernetes-autoscaler:
    bugs: 'https://bugs.launchpad.net/charmed-kubernetes'
    docs: 'https://charmhub.io/kubernetes-autoscaler/docs'
    downstream: charmed-kubernetes/charm-kubernetes-autoscaler.git
    store: 'https://charmhub.io/kubernetes-autoscaler'
    summary: automatically scales up and down a kubernetes cluster
    tags:
      - k8s-operator
      - kubernetes-autoscaler
      - docs-extra
    upstream: 'https://github.com/charmed-kubernetes/charm-kubernetes-autoscaler.git'
- kubernetes-e2e:
    bugs: 'https://bugs.launchpad.net/charm-kubernetes-e2e'
    docs: 'https://charmhub.io/kubernetes-e2e/docs'
    downstream: charmed-kubernetes/charm-kubernetes-e2e.git
    store: 'https://charmhub.io/kubernetes-e2e'
    summary: End-to-end (e2e) tests for Kubernetes
    tags:
      - k8s
      - kubernetes-e2e
      - docs-extra
    upstream: 'https://github.com/charmed-kubernetes/charm-kubernetes-e2e.git'
- kubernetes-control-plane:
    bugs: 'https://bugs.launchpad.net/charm-kubernetes-control-plane'
    build-resources: 'cd {out_path}; bash {src_path}/build-cni-resources.sh'
    docs: 'https://charmhub.io/kubernetes-control-plane/docs'
    downstream: charmed-kubernetes/charm-kubernetes-control-plane.git
    store: 'https://charmhub.io/kubernetes-control-plane'
    summary: The Kubernetes control plane
    tags:
      - k8s
      - kubernetes-control-plane
      - core
    upstream: 'https://github.com/charmed-kubernetes/charm-kubernetes-control-plane.git'
- kubernetes-metrics-server:
    bugs: 'https://bugs.launchpad.net/charmed-kubernetes'
    docs: 'https://charmhub.io/kubernetes-metrics-server/docs'
    downstream: charmed-kubernetes/kubernetes-metrics-server-operator.git
    store: 'https://charmhub.io/kubernetes-metrics-server'
    summary: 'Exposes core Kubernetes metrics via metrics API '
    tags:
      - k8s-operator
      - kubernetes-metrics-server
      - docs-extra
    upstream: >-
      https://github.com/charmed-kubernetes/kubernetes-metrics-server-operator.git
- kubernetes-worker:
    bugs: 'https://bugs.launchpad.net/charm-kubernetes-worker'
    build-resources: 'cd {out_path}; bash {src_path}/build-cni-resources.sh'
    docs: 'https://charmhub.io/kubernetes-worker/docs'
    downstream: charmed-kubernetes/charm-kubernetes-worker.git
    store: 'https://charmhub.io/kubernetes-worker'
    summary: The workload bearing units of a kubernetes cluster
    tags:
      - k8s
      - kubernetes-worker
      - core
    upstream: 'https://github.com/charmed-kubernetes/charm-kubernetes-worker.git'
- tigera-secure-ee:
    bugs: 'https://bugs.launchpad.net/charm-tigera-secure-ee'
    build-resources: 'cd {out_path}; bash {src_path}/build-resources.sh'
    docs: 'https://charmhub.io/tigera-secure-ee/docs'
    downstream: charmed-kubernetes/layer-tigera-secure-ee.git
    store: 'https://charmhub.io/tigera-secure-ee'
    summary: Tigera Secure Enterprise Edition
    tags:
      - k8s
      - tigera-secure-ee
      - cni
    upstream: 'https://github.com/charmed-kubernetes/layer-tigera-secure-ee.git'
- keepalived:
    bugs: 'https://bugs.launchpad.net/charm-keepalived'
    docs: 'https://charmhub.io/keepalived/docs'
    downstream: charmed-kubernetes/charm-keepalived.git
    store: 'https://charmhub.io/keepalived'
    subdir: src
    summary: Failover and monitoring daemon for LVS clusters
    tags:
      - general
      - keepalived
      - k8s
      - docs-extra
    upstream: 'https://github.com/charmed-kubernetes/charm-keepalived.git'
- docker-registry:
    bugs: 'https://bugs.launchpad.net/layer-docker-registry'
    docs: 'https://charmhub.io/docker-registry/docs'
    downstream: charmed-kubernetes/docker-registry-charm.git
    store: 'https://charmhub.io/docker-registry'
    summary: Registry for docker images
    tags:
      - general
      - docker-registry
      - k8s
      - docs-extra
    upstream: 'https://github.com/CanonicalLtd/docker-registry-charm.git'
- aws-iam:
    bugs: 'https://bugs.launchpad.net/charm-aws-iam'
    docs: 'https://charmhub.io/aws-iam/docs'
    downstream: charmed-kubernetes/charm-aws-iam
    store: 'https://charmhub.io/aws-iam'
    summary: ''
    tags:
      - k8s
      - aws-iam
      - docs-extra
    upstream: 'https://github.com/charmed-kubernetes/charm-aws-iam.git'
- azure-integrator:
    bugs: 'https://bugs.launchpad.net/charm-azure-integrator'
    docs: 'https://charmhub.io/azure-integrator/docs'
    downstream: charmed-kubernetes/charm-azure-integrator
    store: 'https://charmhub.io/azure-integrator'
    summary: ''
    tags:
      - k8s
      - charm-azure-integrator
      - integrator
    upstream: 'https://github.com/juju-solutions/charm-azure-integrator.git'
- gcp-integrator:
    bugs: 'https://bugs.launchpad.net/charm-gcp-integrator'
    docs: 'https://charmhub.io/gcp-integrator/docs'
    downstream: charmed-kubernetes/charm-gcp-integrator
    store: 'https://charmhub.io/gcp-integrator'
    summary: Charm which enables Google GCP integrations for Juju
    tags:
      - k8s
      - charm-gcp-integrator
      - integrator
    upstream: 'https://github.com/juju-solutions/charm-gcp-integrator.git'
- github-runner:
    downstream: charmed-kubernetes/github-runner-operator
    tags:
      - github-runner
    upstream: 'https://github.com/charmed-kubernetes/github-runner-operator.git'
- aws-integrator:
    bugs: 'https://bugs.launchpad.net/charm-aws-integrator'
    docs: 'https://charmhub.io/aws-integrator/docs'
    downstream: charmed-kubernetes/charm-aws-integrator
    store: 'https://charmhub.io/aws-integrator'
    summary: Charm to enable AWS integrations via Juju relations.
    tags:
      - k8s
      - charm-aws-integrator
      - integrator
    upstream: 'https://github.com/juju-solutions/charm-aws-integrator.git'
- openstack-integrator:
    bugs: 'https://bugs.launchpad.net/charm-openstack-integrator'
    docs: 'https://charmhub.io/openstack-integrator/docs'
    downstream: charmed-kubernetes/charm-openstack-integrator
    store: 'https://charmhub.io/openstack-integrator'
    summary: Charm which enables OpenStack integrations for Juju
    tags:
      - k8s
      - charm-openstack-integrator
      - integrator
    upstream: 'https://github.com/juju-solutions/charm-openstack-integrator.git'
- vsphere-integrator:
    bugs: 'https://bugs.launchpad.net/charm-vsphere-integrator'
    docs: 'https://charmhub.io/vsphere-integrator/docs'
    downstream: charmed-kubernetes/charm-vsphere-integrator
    store: 'https://charmhub.io/vsphere-integrator'
    summary: Charm which enables vSphere integrations for Juju
    tags:
      - k8s
      - charm-vsphere-integrator
      - integrator
    upstream: 'https://github.com/juju-solutions/charm-vsphere-integrator.git'
- vsphere-cloud-provider:
    bugs: 'https://bugs.launchpad.net/charm-vsphere-cloud-provider'
    docs: 'https://charmhub.io/vsphere-cloud-provider/docs'
    downstream: charmed-kubernetes/vsphere-cloud-provider
    store: 'https://charmhub.io/vsphere-cloud-provider'
    summary: Charm which enables vSphere out of tree provider for Juju
    tags:
      - k8s
      - vsphere-cloud-provider
      - integrator
    upstream: 'https://github.com/charmed-kubernetes/vsphere-cloud-provider.git'
- metallb-controller:
    bugs: 'https://bugs.launchpad.net/operator-metallb'
    docs: 'https://charmhub.io/metallb-controller/docs'
    downstream: charmed-kubernetes/metallb-operator
    store: 'https://charmhub.io/metallb-controller'
    subdir: charms/metallb-controller
    summary: Controller charm for the metallb loadbalancer
    tags:
      - k8s
      - docs-extra
      - metallb
      - metallb-controller
    upstream: 'https://github.com/charmed-kubernetes/metallb-operator.git'
- metallb-speaker:
    bugs: https://bugs.launchpad.net/operator-metallb'
    docs: 'https://charmhub.io/metallb-speaker/docs'
    downstream: charmed-kubernetes/metallb-operator
    store: 'https://charmhub.io/metallb-speaker'
    subdir: charms/metallb-speaker
    summary: Speaker charm for the metallb loadbalancer
    tags:
      - k8s
      - docs-extra
      - metallb
      - metallb-speaker
    upstream: 'https://github.com/charmed-kubernetes/metallb-operator.git'
- multus:
    bugs: 'https://bugs.launchpad.net/charm-multus'
    build-resources: 'cd {src_path}/net-attach-def-manager; ./build'
    docs: 'https://charmhub.io/multus/docs'
    downstream: charmed-kubernetes/charm-multus
    store: 'https://charmhub.io/multus'
    summary: a CNI plugin for attaching multiple network interfaces
    tags:
      - k8s
      - multus
      - cni
    upstream: 'https://github.com/charmed-kubernetes/charm-multus.git'
- sriov-cni:
    bugs: 'https://bugs.launchpad.net/charm-sriov-cni'
    build-resources: 'cd {src_path}/image; ./build'
    docs: 'https://charmhub.io/sriov-cni/docs'
    downstream: charmed-kubernetes/charm-sriov-cni
    store: 'https://charmhub.io/sriov-cni'
    summary: Attach SR-IOV Virtual Functions (VFs) directly to pods
    tags:
      - k8s
      - sriov
      - sriov-cni
      - cni
    upstream: 'https://github.com/charmed-kubernetes/charm-sriov-cni.git'
- sriov-network-device-plugin:
    bugs: 'https://bugs.launchpad.net/charm-sriov-network-device-plugin'
    docs: 'https://charmhub.io/sriov-network-device-plugin/docs'
    downstream: charmed-kubernetes/charm-sriov-network-device-plugin
    store: 'https://charmhub.io/sriov-network-device-plugin'
    summary: Enable SR-IOV support
    tags:
      - k8s
      - sriov
      - sriov-network-device-plugin
      - cni
    upstream: >-
      https://github.com/charmed-kubernetes/charm-sriov-network-device-plugin.git
- coredns:
    bugs: 'https://bugs.launchpad.net/charm-coredns'
    docs: 'https://charmhub.io/coredns/docs'
    downstream: charmed-kubernetes/charm-coredns
    store: 'https://charmhub.io/coredns'
    summary: The CoreDNS domain name service provider
    tags:
      - k8s
      - coredns
      - cni
    upstream: 'https://github.com/charmed-kubernetes/charm-coredns.git'

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
