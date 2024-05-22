# -*- mode:yaml; -*-
# K8s layers
- interface:aws-iam:
    downstream: 'charmed-kubernetes/interface-aws-iam.git'
    upstream: 'https://github.com/charmed-kubernetes/interface-aws-iam'
    tags:
        - k8s
        - interface
        - interface:aws-iam
- interface:mysql:
    downstream: 'charmed-kubernetes/juju-relation-mysql.git'
    upstream: 'https://github.com/johnsca/juju-relation-mysql.git'
    tags:
        - k8s
        - interface
        - interface:mysql
- interface:prometheus:
    downstream: 'charmed-kubernetes/interface-prometheus.git'
    upstream: 'https://git.launchpad.net/interface-prometheus'
    tags:
        - k8s
        - interface
        - interface:prometheus
- interface:prometheus-manual:
    downstream: 'charmed-kubernetes/interface-prometheus-manual.git'
    upstream: 'https://github.com/juju-solutions/interface-prometheus-manual'
    tags:
        - k8s
        - interface
        - interface:prometheus-manual
- interface:grafana-dashboard:
    downstream: 'charmed-kubernetes/interface-grafana-dashboard.git'
    upstream: 'https://github.com/juju-solutions/interface-grafana-dashboard'
    tags:
        - k8s
        - interface
        - interface:grafana-dashboard
- interface:untrusted-container-runtime:
    downstream: 'charmed-kubernetes/interface-untrusted-container-runtime.git'
    upstream: 'https://github.com/charmed-kubernetes/interface-untrusted-container-runtime'
    tags:
        - k8s
        - interface
        - interface:untrusted-container-runtime
- interface:aws-integration:
    downstream: 'charmed-kubernetes/interface-aws-integration.git'
    upstream: 'https://github.com/juju-solutions/interface-aws-integration.git'
    tags:
        - k8s
        - interface
        - interface:aws-integration
- interface:azure-integration:
    downstream: "charmed-kubernetes/interface-azure-integration.git"
    upstream: "https://github.com/juju-solutions/interface-azure-integration.git"
    tags:
        - k8s
        - interface
        - interface:azure-integration
- interface:container-runtime:
    downstream: "charmed-kubernetes/interface-container-runtime.git"
    upstream: "https://github.com/charmed-kubernetes/interface-container-runtime.git"
    tags:
        - k8s
        - interface
        - interface:container-runtime
- interface:dockerhost:
    downstream: "charmed-kubernetes/interface-dockerhost.git"
    upstream: "https://github.com/juju-solutions/interface-dockerhost.git"
    tags:
        - k8s
        - interface
        - interface:dockerhost
- interface:docker-registry:
    downstream: "charmed-kubernetes/interface-docker-registry.git"
    upstream: "https://github.com/juju-solutions/interface-docker-registry.git"
    tags:
        - k8s
        - interface
        - interface:docker-registry
- interface:etcd:
    downstream: "charmed-kubernetes/interface-etcd.git"
    upstream: "https://github.com/juju-solutions/interface-etcd.git"
    tags:
        - k8s
        - interface
        - interface:etcd
- interface:etcd-proxy:
    downstream: "charmed-kubernetes/interface-etcd-proxy.git"
    upstream: "https://github.com/juju-solutions/interface-etcd-proxy.git"
    tags:
        - k8s
        - interface
        - interface:etcd-proxy
- interface:gcp-integration:
    downstream: "charmed-kubernetes/interface-gcp-integration.git"
    upstream: "https://github.com/juju-solutions/interface-gcp-integration.git"
    tags:
        - k8s
        - interface
        - interface:gcp-integration
- interface:hacluster:
    downstream: "charmed-kubernetes/charm-interface-hacluster.git"
    upstream: "https://github.com/openstack/charm-interface-hacluster.git"
    tags:
        - k8s
        - interface
        - interface:hacluster
- interface:http:
    downstream: "charmed-kubernetes/interface-http.git"
    upstream: "https://github.com/juju-solutions/interface-http.git"
    tags:
        - k8s
        - interface:http
        - interface
- interface:juju-info:
    downstream: "charmed-kubernetes/interface-juju-info.git"
    upstream: "https://github.com/juju-solutions/interface-juju-info.git"
    tags:
        - k8s
        - interface
        - interface:juju-info
- interface:kube-control:
    downstream: "charmed-kubernetes/interface-kube-control.git"
    upstream: "https://github.com/juju-solutions/interface-kube-control.git"
    tags:
        - k8s
        - interface
        - interface:kube-control
- interface:kube-dns:
    downstream: "charmed-kubernetes/interface-kube-dns.git"
    upstream: "https://github.com/juju-solutions/interface-kube-dns.git"
    tags:
        - k8s
        - interface
        - interface:kubedns
- interface:kube-masters:
    downstream: "charmed-kubernetes/interface-kube-masters.git"
    upstream: "https://github.com/charmed-kubernetes/interface-kube-masters.git"
    tags:
        - k8s
        - interface
        - interface:kube-masters  # wokeignore:rule=master
- interface:kubernetes-cni:
    downstream: "charmed-kubernetes/interface-kubernetes-cni.git"
    upstream: "https://github.com/juju-solutions/interface-kubernetes-cni.git"
    tags:
        - k8s
        - interface
        - interface:kubernetes-cni
- interface:mount:
    downstream: "charmed-kubernetes/interface-mount.git"
    upstream: "https://github.com/juju-solutions/interface-mount.git"
    tags:
        - k8s
        - interface
        - interface:mount
- interface:nrpe-external-master:
    downstream: "charmed-kubernetes/nrpe-external-master-interface.git"
    upstream: "https://github.com/canonical/nrpe-external-master-interface.git"
    tags:
        - k8s
        - interface
        - interface:nrpe-external-master  # wokeignore:rule=master
- interface:openstack-integration:
    downstream: "charmed-kubernetes/interface-openstack-integration.git"
    upstream: "https://github.com/juju-solutions/interface-openstack-integration.git"
    tags:
        - k8s
        - interface
        - interface:openstack-integration
- interface:peer-discovery:
    downstream: "charmed-kubernetes/charm-interface-peer-discovery.git"
    upstream: "https://github.com/tbaumann/charm-interface-peer-discovery.git"
    tags:
        - k8s
        - interface
        - interface:peer-discovery
- interface:public-address:
    downstream: "charmed-kubernetes/interface-public-address.git"
    upstream: "https://github.com/juju-solutions/interface-public-address.git"
    tags:
        - k8s
        - interface
        - interface:public-address
- interface:sdn-plugin:
    downstream: "charmed-kubernetes/interface-sdn-plugin.git"
    upstream: "https://github.com/juju-solutions/interface-sdn-plugin.git"
    tags:
        - k8s
        - interface
        - interface:sdn-plugin
- interface:tls-certificates:
    downstream: "charmed-kubernetes/interface-tls-certificates.git"
    upstream: "https://github.com/juju-solutions/interface-tls-certificates.git"
    tags:
        - k8s
        - interface
        - interface:tls-certificates
- interface:vault-kv:
    downstream: "charmed-kubernetes/charm-interface-vault-kv.git"
    upstream: "https://github.com/openstack-charmers/charm-interface-vault-kv.git"
    tags:
        - k8s
        - interface
        - interface:vault-kv
- interface:vsphere-integration:
    downstream: "charmed-kubernetes/interface-vsphere-integration.git"
    upstream: "https://github.com/juju-solutions/interface-vsphere-integration.git"
    tags:
        - k8s
        - interface
        - interface:vsphere-integration
- interface:ceph-admin:
    downstream: "charmed-kubernetes/juju-interface-ceph-admin.git"
    upstream: "https://github.com/openstack-charmers/juju-interface-ceph-admin"
    tags:
        - k8s
        - interface
        - interface:ceph-admin
- interface:ceph-client:
    downstream: "charmed-kubernetes/charm-interface-ceph-client.git"
    upstream: "https://github.com/openstack/charm-interface-ceph-client"
    tags:
        - k8s
        - interface
        - interface:ceph-client
- interface:keystone-credentials:
    downstream: "charmed-kubernetes/charm-interface-keystone-credentials.git"
    upstream: "https://github.com/openstack/charm-interface-keystone-credentials"
    tags:
        - k8s
        - interface
        - interface:keystone-credentials
- layer:apt:
    downstream: "charmed-kubernetes/layer-apt.git"
    upstream: "https://git.launchpad.net/layer-apt"
    tags:
        - k8s
        - layer
        - layer:apt
- layer:basic:
    downstream: "charmed-kubernetes/layer-basic.git"
    upstream: "https://github.com/juju-solutions/layer-basic.git"
    tags:
        - k8s
        - layer
        - layer:basic
- layer:cdk-service-kicker:
    downstream: "charmed-kubernetes/layer-cdk-service-kicker.git"
    upstream: "https://github.com/juju-solutions/layer-cdk-service-kicker.git"
    tags:
        - k8s
        - layer
        - layer:cdk-service-kicker
- layer:container-runtime-common:
    downstream: "charmed-kubernetes/layer-container-runtime-common.git"
    upstream: "https://github.com/charmed-kubernetes/layer-container-runtime-common.git"
    tags:
        - k8s
        - layer
        - layer:container-runtime-common
- layer:debug:
    downstream: "charmed-kubernetes/layer-debug.git"
    upstream: "https://github.com/juju-solutions/layer-debug.git"
    tags:
        - k8s
        - layer
        - layer:debug
- layer:docker:
    downstream: "charmed-kubernetes/layer-docker.git"
    upstream: "https://github.com/juju-solutions/layer-docker.git"
    tags:
        - k8s
        - layer
        - layer:docker
- layer:hacluster:
    downstream: "charmed-kubernetes/layer-hacluster.git"
    upstream: "https://github.com/juju-solutions/layer-hacluster.git"
    tags:
        - k8s
        - layer
        - layer:hacluster
- layer:kubernetes-common:
    downstream: "charmed-kubernetes/layer-kubernetes-common"
    upstream: "https://github.com/charmed-kubernetes/layer-kubernetes-common.git"
    tags:
        - k8s
        - layer
        - layer:kubernetes-common
- layer:kubernetes-master-worker-base:
    downstream: "charmed-kubernetes/layer-kubernetes-master-worker-base"
    upstream: "https://github.com/charmed-kubernetes/layer-kubernetes-master-worker-base.git"
    tags:
        - k8s
        - layer
        - layer:kubernetes-master-worker-base  # wokeignore:rule=master
- layer:kubernetes-node-base:
    downstream: "charmed-kubernetes/layer-kubernetes-node-base"
    upstream: "https://github.com/charmed-kubernetes/layer-kubernetes-node-base.git"
    tags:
        - k8s
        - layer
        - layer:kubernetes-node-base
- layer:leadership:
    downstream: "charmed-kubernetes/layer-leadership.git"
    upstream: "https://git.launchpad.net/layer-leadership"
    tags:
        - k8s
        - layer
        - layer:leadership
- layer:metrics:
    downstream: "charmed-kubernetes/layer-metrics.git"
    upstream: "https://github.com/canonical/layer-metrics.git"
    tags:
        - k8s
        - layer
        - layer:metrics
- layer:nagios:
    downstream: "charmed-kubernetes/layer-nagios.git"
    upstream: "https://git.launchpad.net/nagios-layer"
    tags:
        - k8s
        - layer
        - layer:nagios
- layer:nginx:
    downstream: "charmed-kubernetes/juju-layer-nginx.git"
    upstream: "https://github.com/battlemidget/juju-layer-nginx.git"
    tags:
        - k8s
        - layer
        - layer:nginx
- layer:options:
    downstream: "charmed-kubernetes/layer-options.git"
    upstream: "https://github.com/juju-solutions/layer-options.git"
    tags:
        - k8s
        - layer
        - layer:options
- layer:snap:
    downstream: "charmed-kubernetes/layer-snap.git"
    upstream: "https://git.launchpad.net/layer-snap"
    tags:
        - k8s
        - layer
        - layer:snap
- layer:status:
    downstream: "charmed-kubernetes/layer-status.git"
    upstream: "https://github.com/juju-solutions/layer-status.git"
    tags:
        - k8s
        - layer
        - layer:status
- layer:tls-client:
    downstream: "charmed-kubernetes/layer-tls-client.git"
    upstream: "https://github.com/juju-solutions/layer-tls-client.git"
    tags:
        - k8s
        - layer
        - layer:tls-client
- layer:vault-kv:
    downstream: "charmed-kubernetes/layer-vault-kv.git"
    upstream: "https://github.com/juju-solutions/layer-vault-kv.git"
    tags:
        - k8s
        - layer
        - layer:vault-kv
- layer:vaultlocker:
    downstream: "charmed-kubernetes/layer-vaultlocker.git"
    upstream: "https://github.com/juju-solutions/layer-vaultlocker.git"
    tags:
        - k8s
        - layer
        - layer:vaultlocker
- layer:cis-benchmark:
    downstream: "charmed-kubernetes/layer-cis-benchmark.git"
    upstream: "https://github.com/charmed-kubernetes/layer-cis-benchmark.git"
    tags:
        - k8s
        - layer
        - layer:cis-benchmark
- layer:coordinator:
    downstream: "charmed-kubernetes/layer-coordinator.git"
    upstream: "https://git.launchpad.net/layer-coordinator"
    tags:
        - k8s
        - layer
        - layer:coordinator
- layer:index:
    downstream: "charmed-kubernetes/layer-index.git"
    upstream: "https://github.com/juju/layer-index.git"
    needs_stable: no
    needs_tagging: no
    supports_rename: no
    build_cache: no
- lightkube:
    downstream: "canonical/lightkube.git"
    upstream: "https://github.com/gtsystem/lightkube"
    needs_stable: no
    needs_tagging: no
    supports_rename: no
    build_cache: no
