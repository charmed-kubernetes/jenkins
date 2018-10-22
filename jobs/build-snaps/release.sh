#!/bin/bash
#

set -eux

source utilities.sh

# K8s versions we want to check for new releases
declare -a VERSIONS=('latest' '1.10' '1.11' '1.12' '1.13' '1.14' '2.0');

SNAP_INFO_KUBECTL=$(snap info kubectl || true)

function is_upstream_newer_than_edge {
  # Sets $upstream_is_newer to 'yes' when there is a version upstream newer to what we have on edge.
  # Uses snap info on kubectl to find the snap version information
  #
  # Input:
  # $TRACK eg "latest" or "1.11" to check for release
  # $KUBE_VERSION k8s version available upstream for $TRACK
  # $SNAP_INFO_KUBECTL snap command to get the info of kubectl
  #
  # Output:
  # $upstream_is_newer 'yes' when a release upstream is newer that the snap on edge

  local track="$1"
  local kube_version="$2"
  local snap_info_kubectl="$3"

  if [ "${track}" == "latest" ]
  then
    LAST_RELEASE=$(grep ' edge:' <<< "${snap_info_kubectl}"|awk '{print $2}')
  else
    MAIN_VERSION=$(get_major_minor $kube_version)
    LAST_RELEASE=$(grep ${MAIN_VERSION}/edge <<< "${snap_info_kubectl}"|awk '{print $2}')
  fi
  upstream_is_newer='no'
  echo "Last snapped release is ${LAST_RELEASE} and the upstrem release is ${kube_version}"
  if [ v$LAST_RELEASE != $kube_version ] || [ $FORCE_RELEASE = true ]; then
    echo "New release ($KUBE_VERSION) detected."
    upstream_is_newer='yes'
  else
    echo "No new release detected. Latest release is ${LAST_RELEASE}"
  fi
}


function build_and_promote_snaps_to_all_but_stable {
  # Builds and promotes to edge beta and candidate the k8s release found in
  # $KUBE_VERSION. Calls build-and-release-k8s-snaps.sh and promote-snaps.sh.
  #
  # Input:
  # $TRACK eg "latest" or "1.11" to check for release
  # $KUBE_VERSION k8s version available upstream for $TRACK

  local track=$1
  local kube_version=$2

  scripts_path=$(dirname "$0")
  # Build the snaps and push to edge
  export KUBE_VERSION=${kube_version}
  $scripts_path/build.sh

  # Promote snaps from edge to candidate
  version=$(get_major_minor $kube_version)
  export PROMOTE_FROM="$version/edge"
  export PROMOTE_TO="$version/beta $version/candidate"
  if [ "$track" == "latest" ]
  then
    export PROMOTE_TO="edge beta candidate $PROMOTE_TO"
  fi
  $scripts_path/promote.sh
}

function promote_snaps_to_stable {
  # Promotes to stable the snap found in candidate.
  # The following conditions should hold:
  # 1. snap revision should be 7 days old (so no new revisions in 7 days) AND
  # 2. a) There was no previous release OR
  #    b) There is a new release
  #
  # Input:
  # $TRACK eg "latest" or "1.11" to check for release
  # $KUBE_VERSION k8s version available upstream for $TRACK
  # $SNAP_INFO_KUBECTL snap command to get the info of kubectl
  #

    declare -A kube_arch_to_snap_arch=(
      [ppc64le]=ppc64el
      [arm]=armhf
    )


  local track="$1"
  local kube_version="$2"
  local snap_info_kubectl="$3"
  local snapcraft_revisions_kubelet=$(snapcraft revisions --arch="${kube_arch_to_snap_arch[$KUBE_ARCH}:-$KUBE_ARCH}" kubelet)

  if [ "$track" == "latest" ]
  then
    CURRENT_STABLE_RELEASE=$(grep ' stable:' <<< "${snap_info_kubectl}"|awk '{print $2}')
  else
    CURRENT_STABLE_RELEASE=$(grep ${MAIN_VERSION}/stable <<< "${snap_info_kubectl}"|awk '{print $2}')
  fi
  if [ v${CURRENT_STABLE_RELEASE} = ${KUBE_VERSION} ]
  then
    echo 'nothing to promote!'
  else
    # ok, we have a new version, how old is it?
    if [ "$track" == "latest" ]
    then
      release_time_string=$(grep " edge\*"<<< "${snapcraft_revisions_kubelet}"|awk '{print $2}')
    else
      release_time_string=$(grep "${MAIN_VERSION}/edge\*"<<< "${snapcraft_revisions_kubelet}"|awk '{print $2}')
    fi
    release_time=$(date -d "${release_time_string} + 7 days" +%s)
    right_now=$(date +%s)
    if (( right_now >= release_time))
    then
      echo "Promoting mature $kube_version release to stable"
      # Promote snaps from candidate to stable
      scripts_path=$(dirname "$0")
      version=$(get_major_minor $kube_version)
      export PROMOTE_FROM="$version/candidate"
      export PROMOTE_TO="$version/stable"
      if [ "$track" == "latest" ]
      then
        export PROMOTE_TO="stable $PROMOTE_TO"
      fi
      $scripts_path/promote.sh
    else
	echo "Release $kube_version too young to promote to stable"
	echo "Will promote in $(( (release_time - right_now) / 86400 )) days"
    fi
  fi
}


function find_upstream_release_for_track {
  # Finds a suitable release for this version(stable/beta/alpha)
  #
  # Input:
  # ${TRACK} the track we are looking for (eg 1.11) or "latest"
  #
  # Output:
  # ${KUBE_VERSION} the latest release version for the $TRACK passed in
  # ${KUBE_VERSION_IS_STABLE} 'yes' if the release is considered stable upstream
  local track="$1"

  if [ "$track" == "latest" ]
  then
    url="https://dl.k8s.io/release/stable.txt"
  else
    url="https://dl.k8s.io/release/stable-${track}.txt"
  fi

  export KUBE_VERSION="$(curl -s -L $url)"
  export KUBE_VERSION_IS_STABLE='yes'

  if [[ $KUBE_VERSION = *"Error"* ]]
  then
    # We did not get a stable release for the track we are looking for
    # Let's check for unstable ("latest") releases
    url="https://dl.k8s.io/release/latest-${track}.txt"
    export KUBE_VERSION="$(curl -s -L $url)"
    export KUBE_VERSION_IS_STABLE='no'
  fi
}


# Main loop. Go over all versions
for TRACK in ${VERSIONS[@]}
do
  find_upstream_release_for_track "${TRACK}"

  # Work only on the available branches (eg 2.0 might not be there yet)
  if [[ $KUBE_VERSION != *"Error"* ]]
  then
    echo "Processing $KUBE_VERSION"
    is_upstream_newer_than_edge "${TRACK}" "${KUBE_VERSION}" "${SNAP_INFO_KUBECTL}"
    if [ "$upstream_is_newer" == 'yes' ]
    then
      build_and_promote_snaps_to_all_but_stable "${TRACK}" "${KUBE_VERSION}"
    fi

    if [ "$KUBE_VERSION_IS_STABLE" == 'yes' ]
    then
      # Do not promote to stable something it is not stable upstream.
      promote_snaps_to_stable "${TRACK}" "${KUBE_VERSION}" "${SNAP_INFO_KUBECTL}"
    fi
  fi
done
