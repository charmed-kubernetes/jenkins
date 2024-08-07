# -*- mode:yaml; -*-
- calico:
    builder: launchpad
    bugs: 'https://bugs.launchpad.net/charm-calico'
    build-resources: 'cd {out_path}; bash {src_path}/build-calico-resource.sh'
    docs: 'https://charmhub.io/calico/docs'
    downstream: charmed-kubernetes/charm-calico.git
    store: 'https://charmhub.io/calico'
    summary: A robust Software Defined Network from Project Calico
    architectures: [amd64, arm64]
    tags:
      - k8s
      - calico
      - core
      - cni
    upstream: 'https://github.com/charmed-kubernetes/charm-calico.git'
- calico-enterprise:
    builder: launchpad
    bugs: 'https://bugs.launchpad.net/charm-calico-enterprise'
    docs: 'https://charmhub.io/calico-enterprise/docs'
    downstream: charmed-kubernetes/charm-calico-enterprise.git
    store: 'https://charmhub.io/calico-enterprise'
    summary: A robust Software Defined Network from Project Calico
    architectures: [amd64]
    tags:
      - k8s
      - calico-enterprise
      - core
      - cni
    upstream: 'https://github.com/charmed-kubernetes/charm-calico-enterprise.git'
    channel-range:
      min: '1.29'
- canal:
    builder: local
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
- ceph-csi:
    builder: launchpad
    bugs: 'https://bugs.launchpad.net/charm-ceph-csi'
    docs: 'https://charmhub.io/ceph-csi/docs'
    downstream: charmed-kubernetes/ceph-csi-operator.git
    store: 'https://charmhub.io/ceph-csi'
    summary: |
      Deploys Container Storage Interface (CSI) plugin that
      enables Charmed Kubernetes to use ceph as a storage backend.
    tags:
      - k8s-operator
      - ceph-csi
      - docs-extra
    upstream: 'https://github.com/charmed-kubernetes/ceph-csi-operator.git'
    channel-range:
      min: '1.25'
- cinder-csi:
    builder: launchpad
    bugs: 'https://bugs.launchpad.net/charm-cinder-csi'
    docs: 'https://charmhub.io/cinder-csi/docs'
    downstream: charmed-kubernetes/cinder-csi-operator.git
    store: 'https://charmhub.io/cinder-csi'
    summary: Deploys Cinder CSI into a Charmed-Kubernetes cluster
    tags:
      - k8s
      - cinder-csi
      - csi
      - openstack
    upstream: 'https://github.com/canonical/cinder-csi-operator.git'
    channel-range:
      min: '1.28'
- cilium:
    builder: launchpad
    bugs: 'https://bugs.launchpad.net/charm-cilium'
    build-resources: 'cd {out_path}; bash {src_path}/fetch-resources.sh'
    docs: 'https://charmhub.io/cilium/docs'
    downstream: charmed-kubernetes/charm-cilium.git
    store: 'https://charmhub.io/cilium'
    summary: eBPF-based Networking, Observability, Security
    architectures: [amd64, arm64]
    tags:
      - k8s
      - cilium
      - cni
    upstream: 'https://github.com/charmed-kubernetes/charm-cilium.git'
    channel-range:
      min: '1.27'
- containerd:
    builder: local
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
    builder: local
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
    builder: local
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
    builder: local
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
    builder: local
    bugs: 'https://bugs.launchpad.net/charm-kata'
    docs: 'https://charmhub.io/kata/docs'
    downstream: charmed-kubernetes/charm-kata.git
    store: 'https://charmhub.io/kata'
    summary: Kata untrusted container runtime subordinate
    tags:
      - k8s
      - kata
      - cri
      - docs-extra
    upstream: 'https://github.com/charmed-kubernetes/charm-kata.git'
- keystone-k8s-auth:
    builder: launchpad
    bugs: 'https://bugs.launchpad.net/keystone-k8s-auth-operator'
    docs: 'https://charmhub.io/keystone-k8s-auth/docs'
    store: 'https://charmhub.io/keystone-k8s-auth'
    summary: Charm to install the keystone k8s authn and authz deployment
    tags:
      - keystone-k8s-auth
    downstream: canonical/keystone-k8s-auth-operator.git
    upstream: 'https://github.com/canonical/keystone-k8s-auth-operator.git'
- kube-ovn:
    builder: launchpad
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
    channel-range:
      min: '1.25'
- kubeapi-load-balancer:
    builder: launchpad
    bugs: 'https://bugs.launchpad.net/charm-kubeapi-load-balancer'
    docs: 'https://charmhub.io/kubeapi-load-balancer/docs'
    downstream: charmed-kubernetes/charm-kubeapi-load-balancer.git
    build-resources: 'cd {out_path}; bash {src_path}/build-resources.sh'
    store: 'https://charmhub.io/kubeapi-load-balancer'
    summary: Nginx Load Balancer
    tags:
      - k8s
      - kubeapi-load-balancer
      - core
    upstream: 'https://github.com/charmed-kubernetes/charm-kubeapi-load-balancer.git'
- kube-state-metrics:
    builder: launchpad
    bugs: 'https://bugs.launchpad.net/kube-state-metrics-operator'
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
    builder: launchpad
    bugs: 'https://bugs.launchpad.net/charm-kubernetes-autoscaler'
    docs: 'https://charmhub.io/kubernetes-autoscaler/docs'
    downstream: charmed-kubernetes/charm-kubernetes-autoscaler.git
    store: 'https://charmhub.io/kubernetes-autoscaler'
    summary: automatically scales up and down a kubernetes cluster
    tags:
      - kubernetes-autoscaler
      - docs-extra
    upstream: 'https://github.com/charmed-kubernetes/charm-kubernetes-autoscaler.git'
- kubernetes-e2e:
    builder: launchpad
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
    builder: launchpad
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
    builder: launchpad
    bugs: 'https://bugs.launchpad.net/charm-kubernetes-metrics-server'
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
    builder: launchpad
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
- kubevirt:
    builder: launchpad
    bugs: 'https://bugs.launchpad.net/charm-kubevirt'
    docs: 'https://charmhub.io/kubevirt/docs'
    downstream: charmed-kubernetes/charm-kube-virt.git
    store: 'https://charmhub.io/kubevirt'
    summary: Deploys KubeVirt into a Charmed-Kubernetes cluster
    tags:
      - k8s
      - kubevirt
      - docs-extra
    upstream: 'https://github.com/charmed-kubernetes/charm-kube-virt.git'
    channel-range:
      min: '1.27'
- openstack-cloud-controller:
    builder: launchpad
    bugs: 'https://bugs.launchpad.net/charm-openstack-cloud-controller'
    docs: 'https://charmhub.io/openstack-cloud-controller/docs'
    downstream: charmed-kubernetes/openstack-cloud-controller-operator.git
    store: 'https://charmhub.io/openstack-cloud-controller'
    summary: Deploys Openstack Cloud Controller into a Charmed-Kubernetes cluster
    tags:
      - k8s
      - openstack
      - openstack-cloud-controller
    upstream: 'https://github.com/charmed-kubernetes/openstack-cloud-controller-operator.git'
    channel-range:
      min: '1.28'
- tigera-secure-ee:
    builder: local
    bugs: 'https://bugs.launchpad.net/charm-tigera-secure-ee'
    build-resources: 'cd {out_path}; bash {src_path}/build-resources.sh'
    docs: 'https://charmhub.io/tigera-secure-ee/docs'
    downstream: charmed-kubernetes/layer-tigera-secure-ee.git
    store: 'https://charmhub.io/tigera-secure-ee'
    summary: Tigera Secure Enterprise Edition
    tags:
      - tigera-secure-ee
      - cni
    upstream: 'https://github.com/charmed-kubernetes/layer-tigera-secure-ee.git'
    channel-range:
      max: '1.28'
- keepalived:
    builder: local
    bugs: 'https://bugs.launchpad.net/charm-keepalived'
    docs: 'https://charmhub.io/keepalived/docs'
    downstream: charmed-kubernetes/charm-keepalived.git
    store: 'https://charmhub.io/keepalived'
    subdir: src
    summary: Failover and monitoring daemon for LVS clusters
    tags:
      - k8s
      - keepalived
      - docs-extra
    upstream: 'https://github.com/charmed-kubernetes/charm-keepalived.git'
- docker-registry:
    builder: local
    bugs: 'https://bugs.launchpad.net/layer-docker-registry'
    docs: 'https://charmhub.io/docker-registry/docs'
    downstream: charmed-kubernetes/docker-registry-charm.git
    store: 'https://charmhub.io/docker-registry'
    summary: Registry for docker images
    tags:
      - k8s
      - docker-registry
      - docs-extra
    upstream: 'https://github.com/CanonicalLtd/docker-registry-charm.git'
- aws-iam:
    builder: local
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
    builder: local
    bugs: 'https://bugs.launchpad.net/charm-azure-integrator'
    docs: 'https://charmhub.io/azure-integrator/docs'
    downstream: charmed-kubernetes/charm-azure-integrator
    store: 'https://charmhub.io/azure-integrator'
    summary: 'Charm which enables Azure integrations for Juju'
    tags:
      - k8s
      - charm-azure-integrator
      - integrator
    upstream: 'https://github.com/juju-solutions/charm-azure-integrator.git'
- azure-cloud-provider:
    builder: launchpad
    bugs: 'https://bugs.launchpad.net/charm-azure-cloud-provider'
    docs: 'https://charmhub.io/azure-cloud-provider/docs'
    downstream: charmed-kubernetes/charm-azure-cloud-provider
    store: 'https://charmhub.io/azure-cloud-provider'
    summary: 'Charm which enables Azure out-of-tree integrations for Charmed Kubernetes'
    tags:
      - k8s
      - charm-azure-cloud-provider
      - integrator
    upstream: 'https://github.com/charmed-kubernetes/charm-azure-cloud-provider.git'
    channel-range:
      min: '1.25'
- gcp-integrator:
    builder: local
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
- gcp-k8s-storage:
    builder: launchpad
    bugs: 'https://bugs.launchpad.net/charm-gcp-k8s-storage'
    docs: 'https://charmhub.io/gcp-k8s-storage/docs'
    downstream: charmed-kubernetes/gcp-k8s-storage
    store: 'https://charmhub.io/gcp-k8s-storage'
    summary: Charm which enables out-of-tree GCP storage for Charmed Kubernetes.
    tags:
      - k8s
      - gcp-k8s-storage
      - integrator
    upstream: 'https://github.com/charmed-kubernetes/gcp-k8s-storage.git'
    channel-range:
      min: '1.25'
- gcp-cloud-provider:
    builder: launchpad
    bugs: 'https://bugs.launchpad.net/charm-gcp-cloud-provider'
    docs: 'https://charmhub.io/gcp-cloud-provider/docs'
    downstream: charmed-kubernetes/charm-gcp-cloud-provider
    store: 'https://charmhub.io/gcp-cloud-provider'
    summary: 'Charm which enables GCP out-of-tree integrations for Charmed Kubernetes'
    tags:
      - k8s
      - charm-gcp-cloud-provider
      - integrator
    upstream: 'https://github.com/charmed-kubernetes/charm-gcp-cloud-provider.git'
    channel-range:
      min: '1.29'
- github-runner:
    downstream: charmed-kubernetes/github-runner-operator
    tags:
      - github-runner
    upstream: 'https://github.com/charmed-kubernetes/github-runner-operator.git'
- aws-integrator:
    builder: local
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
- aws-k8s-storage:
    builder: launchpad
    bugs: 'https://bugs.launchpad.net/charm-aws-k8s-storage'
    docs: 'https://charmhub.io/aws-k8s-storage/docs'
    downstream: charmed-kubernetes/aws-k8s-storage
    store: 'https://charmhub.io/aws-k8s-storage'
    summary: Charm which enables out-of-tree AWS storage for Charmed Kubernetes.
    tags:
      - k8s
      - aws-k8s-storage
      - integrator
    upstream: 'https://github.com/charmed-kubernetes/aws-k8s-storage.git'
    channel-range:
      min: '1.25'
- aws-cloud-provider:
    builder: launchpad
    bugs: 'https://bugs.launchpad.net/charm-aws-cloud-provider'
    docs: 'https://charmhub.io/aws-cloud-provider/docs'
    downstream: charmed-kubernetes/charm-aws-cloud-provider
    store: 'https://charmhub.io/aws-cloud-provider'
    summary: Charm which enables out-of-tree AWS cloud-provider for Charmed Kubernetes.
    tags:
      - k8s
      - aws-cloud-provider
      - integrator
    upstream: 'https://github.com/charmed-kubernetes/charm-aws-cloud-provider.git'
    channel-range:
      min: '1.27'
- openstack-integrator:
    builder: local
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
    builder: local
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
    builder: launchpad
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
    channel-range:
      min: '1.25'
- metallb:
    builder: launchpad
    bugs: 'https://bugs.launchpad.net/operator-metallb'
    docs: 'https://charmhub.io/metallb/docs'
    downstream: charmed-kubernetes/metallb-operator
    store: 'https://charmhub.io/metallb'
    summary: Metallb loadbalancer charm
    tags:
      - k8s
      - docs-extra
      - metallb
    upstream: 'https://github.com/charmed-kubernetes/metallb-operator.git'
    channel-range:
      min: '1.28'
- metallb-controller:
    bugs: 'https://bugs.launchpad.net/operator-metallb'
    docs: 'https://charmhub.io/metallb-controller/docs'
    downstream: charmed-kubernetes/metallb-operator
    store: 'https://charmhub.io/metallb-controller'
    subdir: charms/metallb-controller
    summary: Controller charm for the metallb loadbalancer
    tags:
      - docs-extra
      - metallb-controller
    upstream: 'https://github.com/charmed-kubernetes/metallb-operator.git'
    channel-range:
      max: '1.27'
- metallb-speaker:
    bugs: 'https://bugs.launchpad.net/operator-metallb'
    docs: 'https://charmhub.io/metallb-speaker/docs'
    downstream: charmed-kubernetes/metallb-operator
    store: 'https://charmhub.io/metallb-speaker'
    subdir: charms/metallb-speaker
    summary: Speaker charm for the metallb loadbalancer
    tags:
      - docs-extra
      - metallb-speaker
    upstream: 'https://github.com/charmed-kubernetes/metallb-operator.git'
    channel-range:
      max: '1.27'
- multus:
    builder: launchpad
    bugs: 'https://bugs.launchpad.net/charm-multus'
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
    builder: launchpad
    bugs: 'https://bugs.launchpad.net/charm-sriov-cni'
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
    builder: launchpad
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
    builder: launchpad
    bugs: 'https://bugs.launchpad.net/charm-coredns'
    docs: 'https://charmhub.io/coredns/docs'
    downstream: charmed-kubernetes/charm-coredns
    store: 'https://charmhub.io/coredns'
    summary: The CoreDNS domain name service provider
    tags:
      - k8s-operator
      - coredns
      - docs-extra
    upstream: 'https://github.com/charmed-kubernetes/charm-coredns.git'
- gatekeeper-controller-manager:
    builder: launchpad
    bugs: 'https://bugs.launchpad.net/opa-gatekeeper-operator'
    docs: 'https://charmhub.io/gatekeeper-controller-manager/docs'
    downstream: charmed-kubernetes/opa-gatekeeper-operators
    store: 'https://charmhub.io/gatekeeper-controller-manager'
    subdir: opa-manager-operator
    summary: Controller charm for Gatekeeper
    tags:
      - k8s-operator
      - gatekeeper-controller-manager
      - docs-extra
    upstream: 'https://github.com/charmed-kubernetes/opa-gatekeeper-operators.git'
- gatekeeper-audit:
    builder: launchpad
    bugs: 'https://bugs.launchpad.net/opa-gatekeeper-operator'
    docs: 'https://charmhub.io/gatekeeper-audit/docs'
    downstream: charmed-kubernetes/opa-gatekeeper-operators
    store: 'https://charmhub.io/gatekeeper-audit'
    subdir: opa-audit-operator
    summary: Audit charm for Gatekeeper audit
    tags:
      - k8s-operator
      - gatekeeper-audit
      - docs-extra
    upstream: 'https://github.com/charmed-kubernetes/opa-gatekeeper-operators.git'
- bird:
    builder: launchpad
    bugs: 'https://bugs.launchpad.net/charm-bird'
    docs: 'https://charmhub.io/bird/docs'
    downstream: charmed-kubernetes/bird-operator
    store: 'https://charmhub.io/bird'
    summary: A dynamic IP routing daemon
    tags:
      - bird
    upstream: 'https://github.com/charmed-kubernetes/bird-operator.git'
    channel-range:
      min: '999.0'
- kubernetes-dashboard:
    builder: launchpad
    bugs: 'https://bugs.launchpad.net/kubernetes-dashboard-operator'
    docs: 'https://charmhub.io/kubernetes-dashboard/docs'
    downstream: charmed-kubernetes/kubernetes-dashboard-operator
    store: 'https://charmhub.io/kubernetes-dashboard'
    summary: A web-based Kubernetes user interface
    tags:
      - k8s-operator
      - kubernetes-dashboard
      - docs-extra
    upstream: 'https://github.com/charmed-kubernetes/kubernetes-dashboard-operator'
    channel-range:
      min: '1.28'
- volcano-admission:
    builder: launchpad
    bugs: 'https://bugs.launchpad.net/charm-volcano'
    docs: 'https://discourse.charmhub.io/t/volcano-docs-index/9600'
    downstream: charmed-kubernetes/charm-volcano
    store: 'https://charmhub.io/volcano-admission'
    summary: Volcano is a batch system built on Kubernetes.
    tags:
      - k8s-operator
      - volcano
      - volcano-admission
      - docs-extra
    upstream: 'https://github.com/charmed-kubernetes/charm-volcano'
    subdir: charms/volcano-admission
    channel-range:
      min: '1.27'
- volcano-controllers:
    builder: launchpad
    bugs: 'https://bugs.launchpad.net/charm-volcano'
    docs: 'https://discourse.charmhub.io/t/volcano-docs-index/9600'
    downstream: charmed-kubernetes/charm-volcano
    store: 'https://charmhub.io/volcano-controllers'
    summary: Volcano is a batch system built on Kubernetes.
    tags:
      - k8s-operator
      - volcano
      - volcano-controllers
      - docs-extra
    upstream: 'https://github.com/charmed-kubernetes/charm-volcano'
    subdir: charms/volcano-controllers
    channel-range:
      min: '1.27'
- volcano-scheduler:
    builder: launchpad
    bugs: 'https://bugs.launchpad.net/charm-volcano'
    docs: 'https://discourse.charmhub.io/t/volcano-docs-index/9600'
    downstream: charmed-kubernetes/charm-volcano
    store: 'https://charmhub.io/volcano-scheduler'
    summary: Volcano is a batch system built on Kubernetes.
    tags:
      - k8s-operator
      - volcano
      - volcano-scheduler
      - docs-extra
    upstream: 'https://github.com/charmed-kubernetes/charm-volcano'
    subdir: charms/volcano-scheduler
    channel-range:
      min: '1.27'
- nvidia-gpu-operator:
    builder: launchpad
    bugs: 'https://bugs.launchpad.net/nvidia-operators'
    downstream: charmed-kubernetes/nvidia
    store: 'https://charmhub.io/nvidia-gpu-operator'
    summary: Simplifies the management of NVIDIA GPU resources in a Kubernetes cluster.
    tags:
      - nvidia
      - nvidia-gpu
    upstream: 'https://github.com/charmed-kubernetes/nvidia'
    subdir: charms/gpu-operator
    channel-range:
      min: '1.29'
- nvidia-network-operator:
    builder: launchpad
    bugs: 'https://bugs.launchpad.net/nvidia-operators'
    downstream: charmed-kubernetes/nvidia
    store: 'https://charmhub.io/nvidia-network-operator'
    summary: Simplifies the management of NVIDIA networking resources in a Kubernetes cluster
    tags:
      - nvidia
      - nvidia-network
    upstream: 'https://github.com/charmed-kubernetes/nvidia'
    subdir: charms/network-operator
    channel-range:
      min: '1.27'


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
