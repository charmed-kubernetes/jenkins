#!/bin/bash
#

set -eux

source utilities.sh

# K8s versions we want to check for new releases
declare -a VERSIONS=('1.6' '1.7' '1.8' '1.9' '1.10' '1.11' '2.0' 'latest');

function check_for_release {
  # Sets $trigger to 'yes' when a new release is available.
  # Looks inside $LAST_RELEASE_FILE and compares the contents with
  # what is in $KUBE_VERSION

  trigger='no'
  if [ -f $LAST_RELEASE_FILE ]
  then
    LAST_RELEASED=`cat $LAST_RELEASE_FILE`
    if [ "$LAST_RELEASED" != "$KUBE_VERSION" ]
    then
      echo "New release ($KUBE_VERSION) detected."
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


function build_promote {
  # Builds and promotes to edge and candidate the k8s release found in
  # $KUBE_VERSION. Calls build-and-release-k8s-snaps.sh and promote-snaps.sh.

  scripts_path=$(dirname "$0")
  # Build the snaps and push to edge
  $scripts_path/build-and-release-k8s-snaps.sh

  # Promote snaps from edge to candidate
  version=$(get_major_minor $KUBE_VERSION)
  export PROMOTE_FROM="$version/edge"
  export PROMOTE_TO="$version/beta $version/candidate"
  if [ "$BRANCH" == "latest" ]
  then
    export PROMOTE_TO="edge beta candidate $PROMOTE_TO"
  fi
  $scripts_path/promote-snaps.sh

  # We are done with promoting the snaps. Lets mark the release.
  echo "$KUBE_VERSION" > $LAST_RELEASE_FILE
}

function promote_stable {
  # Promotes to stable the release found in candidate.
  # The following conditions should hold:
  # 1. $LAST_RELEASE_FILE should be the same the past 7 days AND
  # 2. a) There was not previous release ($STABLE_RELEASED_FILE does not exist) OR
  #    b) There is a new release ($LAST_RELEASE_FILE and $STABLE_RELEASED_FILE differ)

  seven_days_ago=$(date -d 'now - 7 days' +%s)
  last_release_time=$(date -r "$LAST_RELEASE_FILE" +%s)
  stable_promotion='no'
  if (( last_release_time >= seven_days_ago))
  then
    echo "Release $KUBE_VERSION too young to promote to stable"
  elif [ ! -f $STABLE_RELEASE_FILE ] || ! cmp --silent $LAST_RELEASE_FILE $STABLE_RELEASE_FILE
  then
    echo "Promoting mature $KUBE_VERSION release to stable"
    # Promote snaps from edge to candidate
    scripts_path=$(dirname "$0")
    version=$(get_major_minor $KUBE_VERSION)
    export PROMOTE_FROM="$version/candidate"
    export PROMOTE_TO="$version/stable"
    if [ "$BRANCH" == "latest" ]
    then
      export PROMOTE_TO="stable $PROMOTE_TO"
    fi
    $scripts_path/promote-snaps.sh

    stable_promotion='yes'
  fi
}


# Main loop. Go over all versions
for BRANCH in ${VERSIONS[@]}
do
  if [ "$BRANCH" == "latest" ]
  then
    url="https://dl.k8s.io/release/stable.txt"
  else
    url="https://dl.k8s.io/release/stable-${BRANCH}.txt"
  fi
  export BRANCH
  export KUBE_VERSION="$(curl -s -L $url)"
  # LAST_RELEASE_FILE keeps the last release we did to candidate.
  export LAST_RELEASE_FILE="/var/tmp/last_${BRANCH}_k8s_patch_release"
  # STABLE_RELEASED_FILE keeps the last release we did to candidate.
  export STABLE_RELEASE_FILE="/var/tmp/last_${BRANCH}_k8s_patch_release.to_stable"

  # Work only on the available branches (eg 2.0 might not be there yet)
  if [[ $KUBE_VERSION != *"Error"* ]]
  then
    echo "Processing $KUBE_VERSION"
    check_for_release
    if [ "$trigger" == 'yes' ]
    then
      build_promote
      echo "$KUBE_VERSION" > $LAST_RELEASE_FILE
    fi

    promote_stable
    if [ "$stable_promotion" == 'yes' ]
    then
      echo "$KUBE_VERSION" > $STABLE_RELEASE_FILE
    fi
  fi
done
