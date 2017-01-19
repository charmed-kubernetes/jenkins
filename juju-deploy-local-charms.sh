#!/usr/bin/env bash
# Deploys a kubernetes bundle, and the kubernetes-e2e charm adding relations.

set -o errexit  # Exit when an individual command fails.
set -o pipefail  # The exit status of the last command is returned.
set -o xtrace  # Print the commands that are executed.

echo "${0} started at `date`."

# First argument is the model namme for this build.
MODEL=${1:-"model-is-undefined"}

# Define the juju and in-jujubox functions.
source ./define-juju.sh

# Some of the files in JUJU_DATA my not be owned by the ubuntu user, fix that.
CHOWN_CMD="sudo chown -R ubuntu:ubuntu /home/ubuntu/.local/share/juju"
# Create a model just for this run of the tests.
in-jujubox "${CHOWN_CMD} && juju add-model ${MODEL}"

# Make the charms owned by the ubuntu user.
CHOWN_CMD="sudo chown -R ubuntu:ubuntu /home/ubuntu/charms"
# Set test mode on the deployment so we dont bloat charm-store deployment count
in-jujubox "${CHOWN_CMD} && juju model-config -m ${MODEL} test-mode=1"

# TODO we could alternately use the local.yaml of bundle-canonical-kubernetes.
# Deploy the kubernetes charms with the jujubox path.
juju deploy /home/ubuntu/charms/builds/easyrsa
juju deploy /home/ubuntu/charms/builds/etcd
juju deploy /home/ubuntu/charms/builds/flannel
#juju deploy /home/ubuntu/charms/builds/kubeapi-load-balancer
juju deploy /home/ubuntu/charms/builds/kubernetes-e2e
juju deploy /home/ubuntu/charms/builds/kubernetes-master
juju deploy /home/ubuntu/charms/builds/kubernetes-worker -n 2
# Expose the load balancer and the worker.
#juju expose kubeapi-load-balancer
juju expose kubernetes-worker
# Add the relations.
#juju add-relation kubernetes-master:kube-api-endpoint kubeapi-load-balancer:apiserver
#juju add-relation kubernetes-master:loadbalancer kubeapi-load-balancer:loadbalancer
juju add-relation kubernetes-master:cluster-dns kubernetes-worker:kube-dns
juju add-relation kubernetes-master easyrsa
juju add-relation kubernetes-master etcd
juju add-relation kubernetes-master flannel
juju add-relation kubernetes-worker easyrsa
juju add-relation kubernetes-worker flannel
#juju add-relation kubernetes-worker kubeapi-load-balancer
juju add-relation kubernetes-worker:kube-api-endpoint kubernetes-master:kube-api-endpoint
juju add-relation kubernetes-e2e kubernetes-master
juju add-relation kubernetes-e2e easyrsa
juju add-relation etcd easyrsa
juju add-relation flannel etcd
#juju add-relation kubeapi-load-balancer easyrsa

echo "${0} completed successfully at `date`."
