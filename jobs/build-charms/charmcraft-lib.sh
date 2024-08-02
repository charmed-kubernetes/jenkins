#!/bin/bash
set -eux

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
  until sudo lxc shell $charmcraft_lxc -- bash -c "snap install charmcraft --classic --channel=2.x/stable"; do
    echo 'retrying charmcraft install in 3s...'
    sleep 3
  done

  local clone_current="git clone $(git remote -v | grep http | head -n 1 | awk '{print $2}') clone-test"
  if sudo lxc shell $charmcraft_lxc -- bash -c "$clone_current"; then
    echo "$charmcraft_lxc can clone a repo"
  else
    echo "$charmcraft_lxc can't clone a repo, try setting proxy..."
    sudo lxc shell $charmcraft_lxc -- bash -c 'git config --global --add http.proxy http://squid.internal:3128'
    sudo lxc shell $charmcraft_lxc -- bash -c 'git config --global --add https.proxy http://squid.internal:3128'
    sudo lxc shell $charmcraft_lxc -- bash -c "$clone_current"
  fi
  sudo lxc shell $charmcraft_lxc -- bash -c 'rm -rf clone-test'

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
  sudo lxc shell $charmcraft_lxc -- bash -c "cd charm/$subdir; cat version || git rev-parse --short HEAD | tee version"
  sudo lxc shell $charmcraft_lxc --env CHARMCRAFT_MANAGED_MODE=1 -- bash -c "cd charm; charmcraft pack -v -p $subdir"
}

ci_charmcraft_release()
{
  # Upload to CharmHub, and optionally release
  local charmcraft_lxc=$1
  local do_release_to_edge=${2:-}
  local upload_args=$([[ $do_release_to_edge == 'true' ]] && echo ' --release edge')
  sudo lxc shell $charmcraft_lxc --env CHARMCRAFT_AUTH="$CHARMCRAFT_AUTH" -- bash -c "cd charm; charmcraft upload *.charm $upload_args"
}

ci_charmcraft_copy()
{
  # Copy charm out of the container to a local directory
  local charmcraft_lxc=$1
  local copy_destination=$2
  for charm in $(sudo lxc exec $charmcraft_lxc -- bash -c "ls /root/charm/*.charm"); do
    echo "Pulling ${charmcraft_lxc}${charm} to ${copy_destination}"
    sudo lxc file pull ${charmcraft_lxc}${charm} ${copy_destination}
  done
}

ci_charmcraft_promote()
{
  # Promote an existing charm revision to a channel
  local charmcraft_lxc=$1
  local charm=$2
  local revision=$3
  local channel=$4
  sudo lxc shell $charmcraft_lxc --env CHARMCRAFT_AUTH="$CHARMCRAFT_AUTH" -- bash -c "charmcraft release $charm --revision $revision --channel $channel"
}
