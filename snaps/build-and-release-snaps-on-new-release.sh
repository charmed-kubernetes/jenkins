#!/bin/bash
#

KUBE_VERSION="${KUBE_VERSION:-$(curl -L https://dl.k8s.io/release/stable.txt)}"
# LAST_RELEASE_FILE keeps the last release we did.
LAST_RELEASE_FILE="/var/tmp/last_k8s_patch_release"


function check_for_release {
  trigger='no'
  if [ -f $LAST_RELEASE_FILE ]
  then
    LAST_RELEASED=`cat $LAST_RELEASE_FILE`
    if [ "$LAST_RELEASED" != "$KUBE_VERSION" ]
    then
      echo "New release ($KUBE_VERSION) detected."
      echo "$KUBE_VERSION" > $LAST_RELEASE_FILE
      trigger='yes'
    else
      echo "No new release detected. Latest release is $LAST_RELEASED."
      trigger='no'
    fi
  else
    echo "Bootstrapping trigger with kubernetes version $KUBE_VERSION."
    echo "Releases following $KUBE_VERSION will trigger the snap release process."
    echo "$KUBE_VERSION" > $LAST_RELEASE_FILE
    trigger='init'
  fi
}


check_for_release
if [ "$trigger" == 'yes' ]
then
  scripts_path=$(dirname "$0")
  # Build the snaps and push to edge
  $scripts_path/build-and-release-k8s-snaps.sh

  if [ "$?" == 0 ]
  then
    # Promote snaps from edge to candidate
    version=${KUBE_VERSION:1:3}
    export PROMOTE_FROM="$version/edge"
    export PROMOTE_TO="$version/candidate"
    export FAKE_PROMOTE="no"
    $scripts_path/promote-snaps.sh
  fi
fi
