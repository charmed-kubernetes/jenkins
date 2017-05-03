#!/usr/bin/env bash
# Bundletest cdk

set -o errexit  # Exit when an individual command fails.
set -o pipefail  # The exit status of the last command is returned.
set -o xtrace  # Print the commands that are executed.

echo "Moving ${BUNDLE_NAME_AND_REVISION} from ${FROM_CHANNEL} to ${TO_CHANNEL} at `date`."

################################################
# Validate params:
################################################

if [ -z "${BUNDLE_NAME_AND_REVISION}" ]; then
  echo "Please provide bundle and revision."
  exit 1
fi

################################################
# Utils
################################################

function get_charm() {
  CHARM_NAME=$@
  CHARM=`charm show ${BUNDLE_NAME_AND_REVISION} --channel ${FROM_CHANNEL} | grep Charm | grep ${CHARM_NAME} | awk '{print $2}'`
  echo ${CHARM}
}


function easyrsa_resource() {
  CHARM=$@
  RESOURCE_REV=`charm show ${CHARM} --channel ${FROM_CHANNEL} resources | grep Revision | awk '{print $2}'`
  echo "easyrsa-${RESOURCE_REV}"
}


function flannel_resource() {
  CHARM=$@
  RESOURCE_REV=`charm show ${CHARM} --channel ${FROM_CHANNEL} resources | grep Revision | awk '{print $2}'`
  echo "flannel-${RESOURCE_REV}"
}


##################################
# Release charms and bundle
##################################


# Kubernetes master
MASTER_CHARM=$(get_charm kubernetes-master)
echo "Releasing ${MASTER_CHARM}"
charm release ${MASTER_CHARM} --channel ${TO_CHANNEL} -r cdk-addons-0 -r kube-apiserver-0 -r kube-controller-manager-0 -r kube-scheduler-0 -r kubectl-0
charm grant ${MASTER_CHARM} everyone --channel ${TO_CHANNEL}


# Kubernetes worker
WORKER_CHARM=$(get_charm kubernetes-worker)
echo "Releasing ${WORKER_CHARM}"
charm release ${WORKER_CHARM} --channel ${TO_CHANNEL} -r cni-0 -r kube-proxy-0 -r kubectl-0 -r kubelet-0
charm grant ${WORKER_CHARM} everyone --channel ${TO_CHANNEL}

# Easyrsa
EASY_CHARM=$(get_charm easyrsa)
RESOURCE=$(easyrsa_resource ${EASY_CHARM})
echo "Releasing ${EASY_CHARM} with ${RESOURCE}"
charm release ${EASY_CHARM} --channel ${TO_CHANNEL} -r ${RESOURCE}
charm grant ${EASY_CHARM} everyone --channel ${TO_CHANNEL}

# Etcd
ETCD_CHARM=$(get_charm etcd)
echo "Releasing ${ETCD_CHARM}"
charm release ${ETCD_CHARM} --channel ${TO_CHANNEL} -r etcd-3 -r snapshot-0
charm grant ${ETCD_CHARM} everyone --channel ${TO_CHANNEL}

# Flannel
FLANNEL_CHARM=$(get_charm flannel)
RESOURCE=$(flannel_resource ${FLANNEL_CHARM})
echo "Releasing ${FLANNEL_CHARM} with  ${RESOURCE}"
charm release ${FLANNEL_CHARM} --channel ${TO_CHANNEL} -r ${RESOURCE}
charm grant ${FLANNEL_CHARM} everyone --channel ${TO_CHANNEL}


if [[ ${BUNDLE_NAME_AND_REVISION} == *"canonical-kubernetes"* ]]; then
  # Kube api LB
  LB_CHARM=$(get_charm kubeapi-load-balancer)
  echo "Releasing ${LB_CHARM}"
  charm release ${LB_CHARM} --channel ${TO_CHANNEL}
  charm grant ${LB_CHARM} everyone --channel ${TO_CHANNEL}
fi


echo "Releasing Bundle ${BUNDLE_NAME_AND_REVISION}"
charm release ${BUNDLE_NAME_AND_REVISION} --channel ${TO_CHANNEL}
charm grant ${BUNDLE_NAME_AND_REVISION} everyone --channel ${TO_CHANNEL}

