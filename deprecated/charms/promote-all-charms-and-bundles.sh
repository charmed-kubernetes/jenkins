#!/usr/bin/env bash
set -eux

CHARMS="
  cs:~containers/easyrsa
  cs:~containers/etcd
  cs:~containers/flannel
  cs:~containers/calico
  cs:~containers/canal
  cs:~containers/kubernetes-master
  cs:~containers/kubernetes-worker
  cs:~containers/kubeapi-load-balancer
  cs:~containers/kubernetes-e2e
  cs:~containers/kubernetes-core
  cs:~containers/canonical-kubernetes
  cs:~containers/canonical-kubernetes-elastic
  cs:~containers/kubernetes-calico
  cs:~containers/canonical-kubernetes-canal
"

for charm in $CHARMS; do
  CHARM="$charm" FROM_CHANNEL="$FROM_CHANNEL" TO_CHANNEL="$TO_CHANNEL" ./charms/promote-charm.sh
done
