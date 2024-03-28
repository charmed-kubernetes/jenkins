#!/bin/bash
set -eux

if [[ $0 == $BASH_SOURCE ]]; then
  echo "$0 should be sourced";
  exit
fi
echo "sourced ${BASH_SOURCE:-$0}"


unitAddress()
{
    py_script="
import sys
import yaml

status_yaml=yaml.safe_load(sys.stdin)
unit = status_yaml['applications']['$1']['units']
units = list(unit.keys())
print(unit[units[0]]['public-address'])
"
    juju status -m "$JUJU_CONTROLLER:$JUJU_MODEL" "$1" --format yaml | env python3 -c "$py_script"
}

# Grabs current directory housing script ($0)
#
# Arguments:
# $0: current script
scriptPath() {
    env python3 -c "import os,sys; print(os.path.dirname(os.path.abspath(\"$0\")))"
}

ci_docker_status()
{
    # Get details of an authenticated dockerhub request

    set +x
    local user=$1
    local pass=$2
    local token=$(curl --user "${user}:${pass}" \
        "https://auth.docker.io/token?service=registry.docker.io&scope=repository:ratelimitpreview/test:pull" | \
        jq -r .token)
    curl --head -H "Authorization: Bearer ${token}" \
        https://registry-1.docker.io/v2/ratelimitpreview/test/manifests/latest 2>&1
    set -x
}

ci_lxc_launch()
{
    # Launch local LXD container to publish to charmcraft
    local lxc_image=$1
    local lxc_container=$2
    sudo lxc init ${lxc_image} ${lxc_container} ${@:3}
    printf "uid $(id -u) 1000\ngid $(id -g) 1000" | sudo lxc config set ${lxc_container} raw.idmap -
    sudo lxc start ${lxc_container}
    sleep 10
    ci_lxc_apt_install_retry ${lxc_container} build-essential snapd
}

ci_lxc_mount()
{
    # create a directory path within the container and mount a local directory into it
    local lxc_container=$1
    local name=$2
    local source=$3
    local dest=$4
    sudo lxc exec ${lxc_container} -- mkdir -p ${dest}
    sudo lxc config device add ${lxc_container} ${name} disk source=${source} path=${dest}
}

ci_lxc_push()
{
    # copy a file from the host into the container
    local lxc_container=$1
    local source=$2
    local dest=$3
    local args=(-p --mode "$(stat -c '0%a' $source)")
    if [ "$(stat -c '%U' $source)" == "$(whoami)" ]; then
        args+=(--uid 1000)
    fi
    if [ "$(stat -c '%G' $source)" == "$(whoami)" ]; then
        args+=(--gid 1000)
    fi
    sudo lxc file push "${args[@]}" ${source} ${lxc_container}/${dest}
}


ci_lxc_delete()
{
    # Stop and delete containers matching a prefix
    local lxc_container_prefix=$1
    local existing_containers=$(sudo lxc list -c n -f csv "${lxc_container_prefix}" | xargs)
    echo "Removing containers: ${existing_containers}"
    set +e
    sudo lxc delete --force "${existing_containers}"
    set -e
}

ci_lxc_exec(){ sudo lxc exec ${@}; }  # exec in a lxc container

ci_lxc_exec_user(){ ci_lxc_exec --user=1000 --group=1000 ${@}; } # exec as ubuntu in a lxc container

ci_lxc_apt_install()
{
    # install debs with apt in a container
    local lxc_container=$1
    ci_lxc_exec ${lxc_container} -- apt update -y
    ci_lxc_exec ${lxc_container} -- apt install -y ${@:2}
}

ci_lxc_snap_install()
{
    # install a single snap in a container
    local lxc_container=$1
    ci_lxc_exec ${lxc_container} -- snap install ${@:2}
}

ci_lxc_apt_install_retry()
{
    local next_wait=5
    until [ ${next_wait} -eq 10 ] || ci_lxc_apt_install $@; do
        echo "Retrying lxc apt-install in ${next_wait}s..."
        sleep $(( next_wait++ ))
    done
    [ ${next_wait} -lt 10 ]
}

ci_lxc_snap_install_retry()
{
    local next_wait=5
    until [ ${next_wait} -eq 10 ] || ci_lxc_snap_install $@; do
        echo "Retrying lxc snap-install in ${next_wait}s..."
        sleep $(( next_wait++ ))
    done
    [ ${next_wait} -lt 10 ]
}