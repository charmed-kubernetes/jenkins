#!/usr/bin/env bash
set -eux

CHARMS="
  cs:~containers/easyrsa
  cs:~containers/etcd
  cs:~containers/flannel
  cs:~containers/kubernetes-master
  cs:~containers/kubernetes-worker
  cs:~containers/kubeapi-load-balancer
  cs:~containers/kubernetes-e2e
  cs:~containers/kubernetes-core
  cs:~containers/canonical-kubernetes
"

for charm in $CHARMS; do
  CHARM="$charm" FROM_CHANNEL="$FROM_CHANNEL" TO_CHANNEL="$TO_CHANNEL" ./charms/promote-charm.sh
done
