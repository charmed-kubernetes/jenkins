#!/usr/bin/env bash

# The current build number, such as "153"
export BUILD_NUMBER=${BUILD_NUMBER:-"153"}

# The cloud to test on.
export CLOUD=${CLOUD:-"aws"}

# Name of the project of this build, such as "foo" or "foo/bar".
export JOB_NAME=${JOB_NAME:-"foo"}

# String of "jenkins-${JOB_NAME}-${BUILD_NUMBER}".
export BUILD_TAG=${BUILD_TAG:-"hudson-${JOB_NAME}-${BUILD_NUMBER}"}

# Secrets file handled by Jenkins.
export JUJU_DATA_TAR=${JUJU_GCE_DATA:-"${HOME}/.ssh/juju_${CLOUD}.tar.gz"}

# Secrets file handled by Jenkins.
export GCE_ACCOUNT_CREDENTIAL=${GCE_ACCOUNT_CREDENTIAL:-"${HOME}/.ssh/gce.json"}

# The absolute path of the directory assigned to the build as a workspace.
export WORKSPACE=${WORKSPACE:-"/tmp/workspace"}

if [[ ! -d ${WORKSPACE} ]]; then
  mkdir -p ${WORKSPACE}
  # Uncompress the credentials to workspace/juju to be used by other scripts.
  tar -xvzf $JUJU_DATA_TAR -C $WORKSPACE
fi 

export JUJU_DATA=${WORKSPACE}/juju
