#!/bin/bash
#

set -eux

source utilities.sh

# K8s versions we want to check for new releases
declare -a VERSIONS=('1.6' '1.7' '1.8' '1.9' '1.10' '1.11' '1.12' '1.13' '1.14' '2.0' 'latest');

SNAP_INFO_KUBECTL=$(snap info kubectl)
SNAPCRAFT_REVISIONS_KUBELET=$(snapcraft revisions --arch=amd64 kubelet)

function check_for_release {
  # Sets $trigger to 'yes' when a new release is available.
  # Compares snap info on kubectl to find version information

  if [ "$BRANCH" == "latest" ]
  then
    LAST_RELEASE=$(grep ' edge:' <<< "${SNAP_INFO_KUBECTL}"|awk '{print $2}')
  else
    MAIN_VERSION=$(get_major_minor $KUBE_VERSION)
    LAST_RELEASE=$(grep ${MAIN_VERSION}/edge <<< "${SNAP_INFO_KUBECTL}"|awk '{print $2}')
  fi
  trigger='no'
  echo "Last release is ${LAST_RELEASE} and this release is ${KUBE_VERSION}"
  if [ v$LAST_RELEASE != $KUBE_VERSION ]
  then
    echo "New release ($KUBE_VERSION) detected."
    trigger='yes'
  else
    echo "No new release detected. Latest release is ${LAST_RELEASE}"
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
}

function promote_stable {
  # Promotes to stable the release found in candidate.
  # The following conditions should hold:
  # 1. snap revision should be 7 days old(so no new revisions in 7 days) AND
  # 2. a) There was not previous release OR
  #    b) There is a new release

  stable_promotion='no'
  if [ "$BRANCH" == "latest" ]
  then
    CURRENT_STABLE_RELEASE=$(grep ' stable:' <<< "${SNAP_INFO_KUBECTL}"|awk '{print $2}')
  else
    CURRENT_STABLE_RELEASE=$(grep ${MAIN_VERSION}/stable <<< "${SNAP_INFO_KUBECTL}"|awk '{print $2}')
  fi
  if [ v${CURRENT_STABLE_RELEASE} = ${KUBE_VERSION} ]
  then
    echo 'nothing to promote!'
  else
    # ok, we have a new version, how old is it?
    if [ "$BRANCH" == "latest" ]
    then
      release_time_string=$(grep " edge\*"<<< "${SNAPCRAFT_REVISIONS_KUBELET}"|awk '{print $2}')
    else
      release_time_string=$(grep "${MAIN_VERSION}/edge\*"<<< "${SNAPCRAFT_REVISIONS_KUBELET}"|awk '{print $2}')
    fi
    release_time=$(date -d "${release_time_string} + 7 days" +%s)
    right_now=$(date +%s)
    if (( right_now >= release_time))
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
    else
	echo "Release $KUBE_VERSION too young to promote to stable"
	echo "Will promote in $(( (release_time - right_now) / 86400 )) days"
    fi
  fi
}


function find_release {
  # Finds a suitable release for this version(stable/beta/alpha)
  if [ "$1" == "latest" ]
  then
    url="https://dl.k8s.io/release/stable.txt"
  else
    url="https://dl.k8s.io/release/stable-${BRANCH}.txt"
  fi

  export KUBE_VERSION="$(curl -s -L $url)"
  export KUBE_VERSION_URL=$url

  if [[ $KUBE_VERSION = *"Error"* ]]
  then
    if [ "$1" == "latest" ]
    then
      url="https://dl.k8s.io/release/latest.txt"
    else
      url="https://dl.k8s.io/release/latest-${BRANCH}.txt"
    fi

    export KUBE_VERSION="$(curl -s -L $url)"
    export KUBE_VERSION_URL=$url
  fi
}


# Main loop. Go over all versions
for BRANCH in ${VERSIONS[@]}
do
  find_release "${BRANCH}"

  export BRANCH

  # Work only on the available branches (eg 2.0 might not be there yet)
  if [[ $KUBE_VERSION != *"Error"* ]]
  then
    echo "Processing $KUBE_VERSION"
    check_for_release
    if [ "$trigger" == 'yes' ]
    then
      build_promote
    fi

    promote_stable
  fi
done
