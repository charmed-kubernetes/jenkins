#!/usr/bin/env bash
set -eux

export GIT_REPO="${GIT_REPO:-https://github.com/kubernetes/kubernetes.git}"

echo "${0} started at `date`."

# Set the Juju envrionment variables for this script.
export JUJU_REPOSITORY=${WORKSPACE}/build/charms
mkdir -p ${JUJU_REPOSITORY}

# The cloud is an option for this script, default to gce.
CLOUD=${CLOUD:-"google"}


# Clone the git repo
if ! [ -d kubernetes ]; then
  git clone ${GIT_REPO}
fi

# Build the charm with no local layers
cd kubernetes/cluster/juju/layers/kubernetes-master
charm build -r --no-local-layers --force
cd ..

if [ ${RUN_TESTS} = true ]; then
  JUJU_CONTROLLER="jenkins-ci-${CLOUD}"
  juju switch ${JUJU_CONTROLLER}

  MODEL="build-and-release-kubernetes-master-${BUILD_NUMBER}"
  # Create a model just for this run of the tests.
  juju add-model ${MODEL}
  # makesure you do not try to delete the model immediately
  sleep 10
  # Catch all EXITs from this script and make sure to destroy the model.
  trap "juju destroy-model -y ${MODEL} || true" EXIT
  # Set test mode on the deployment so we dont bloat charm-store deployment count
  juju model-config -m ${MODEL} test-mode=1
  juju switch ${MODEL}
  bundletester -vF -l DEBUG -t ${JUJU_REPOSITORY}/builds/kubernetes-master -o report.xml -r xml
fi

# Create an empty reports file in case tests were skipped
touch report.xml

if [ ${RELEASE} = true ]; then
  CHARM=$(/usr/bin/charm push $JUJU_REPOSITORY/builds/kubernetes-master cs:~containers/kubernetes-master | head -n 1 | awk '{print $2}')
  echo "Releasing ${CHARM}"
  charm release ${CHARM} --channel ${RELEASE_TO_CHANNEL} -r cdk-addons-0 -r kube-apiserver-0 -r kube-controller-manager-0 -r kube-scheduler-0 -r kubectl-0
  charm grant ${CHARM} everyone --channel ${RELEASE_TO_CHANNEL}
fi
