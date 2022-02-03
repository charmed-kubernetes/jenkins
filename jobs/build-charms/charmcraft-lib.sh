#!/bin/bash -eux

if [[ $0 == $BASH_SOURCE ]]; then
  echo "$0 should be sourced";
  exit
fi
echo "sourced ${BASH_SOURCE:-$0}"
source $(dirname ${BASH_SOURCE:-$0})/../../cilib.sh

ci_charmcraft_launch()
{
  # Launch local LXD container to publish to charmcraft
  local charmcraft_lxc=$1
  ci_lxc_launch ubuntu:20.04 $charmcraft_lxc
  until sudo lxc shell $charmcraft_lxc -- bash -c 'snap install charmcraft --classic'; do
    echo 'retrying charmcraft install in 3s...'
    sleep 3
  done
}

ci_charmcraft_pack()
{
  # Build charm
  local charmcraft_lxc=$1
  local repository=$2
  local branch=$3
  local subdir=${4:-.}
  sudo lxc shell $charmcraft_lxc -- bash -c "rm -rf /root/*"
  sudo lxc shell $charmcraft_lxc -- bash -c "git clone ${repository} -b ${branch} charm"
  sudo lxc shell $charmcraft_lxc -- bash -c "cd charm/$subdir; cat version || git describe --dirty --always | tee version"
  sudo lxc shell $charmcraft_lxc --env CHARMCRAFT_MANAGED_MODE=1 -- bash -c "cd charm; charmcraft pack -v -p $subdir"
}

ci_charmcraft_release()
{
  # Upload to CharmHub, and optionally release
  local charmcraft=$1
  local do_release_to_edge=${2:-}
  local upload_args=$([[ $do_release_to_edge == 'true' ]] && echo ' --release edge')
  sudo lxc shell $charmcraft --env CHARMCRAFT_AUTH="$CHARMCRAFT_AUTH" -- bash -c "cd charm; charmcraft upload *.charm $upload_args"
}

ci_charmcraft_copy()
{
  # Copy charm out of the container to a local directory
  local charmcraft=$1
  local copy_destination=$2
  for charm in $(sudo lxc exec $charmcraft -- bash -c "ls /root/charm/*.charm"); do
    echo "Pulling ${container}${charm} to ${copy_destination}"
    sudo lxc file pull ${container}${charm} ${copy_destination}
  done
}