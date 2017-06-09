#!/usr/bin/env bash
set -eux

export GIT_REPO="${GIT_REPO:-https://github.com/juju-solutions/layer-etcd.git}"

source utils/retry.sh

echo "${0} started at `date`."

# Set the Juju envrionment variables for this script.
export JUJU_REPOSITORY=${WORKSPACE}/build/charms
mkdir -p ${JUJU_REPOSITORY}

# The cloud is an option for this script, default to gce.
CLOUD=${CLOUD:-"google"}


# Clone the git repo
git clone ${GIT_REPO}

# Build the charm with no local layers
cd layer-etcd
retry charm build -r --no-local-layers --force
cd ..

if [ ${RUN_TESTS} = true ]; then
  JUJU_CONTROLLER="jenkins-ci-${CLOUD}"
  juju switch ${JUJU_CONTROLLER}

  MODEL="build-and-release-etcd-${BUILD_NUMBER}"
  # Create a model just for this run of the tests.
  juju add-model ${MODEL}
  # makesure you do not try to delete the model immediately
  sleep 10
  # Catch all EXITs from this script and make sure to destroy the model.
  trap "juju destroy-model -y ${MODEL} || true" EXIT
  # Set test mode on the deployment so we dont bloat charm-store deployment count
  juju model-config -m ${MODEL} test-mode=1
  juju switch ${MODEL}
  bundletester -vF -l DEBUG -t ${JUJU_REPOSITORY}/builds/etcd -o report.xml -r xml
fi

# Create an empty reports file in case tests were skipped
touch report.xml

if [ ${RELEASE} = true ]; then
  ETCD_CHARM=$(/usr/bin/charm push $JUJU_REPOSITORY/builds/etcd cs:~containers/etcd | head -n 1 | awk '{print $2}')
  echo "Releasing ${ETCD_CHARM}"
  CHARM="$ETCD_CHARM" FROM_CHANNEL=unpublished TO_CHANNEL=edge ./charms/promote-charm.sh
fi
