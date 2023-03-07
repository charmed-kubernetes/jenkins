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
    sudo lxc launch ${lxc_image} ${lxc_container} ${@:3}
    sleep 10
    printf "uid $(id -u) 1000\ngid $(id -g) 1000" | sudo lxc config set ${lxc_container} raw.idmap -
    sudo lxc restart ${lxc_container}
    ci_lxc_apt_install ${lxc_container} build-essential
}

ci_lxc_mount()
{
    local lxc_container=$1
    local name=$2
    local source=$3
    local dest=$4
    sudo lxc exec ${lxc_container} -- mkdir -p ${dest}
    sudo lxc config device add ${lxc_container} ${name} disk source=${source} path=${dest}
}

ci_lxc_push()
{
    local lxc_container=$1
    local source=$2
    local dest=$3
    sudo lxc file push ${source} ${lxc_container}/${dest}
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

ci_lxc_exec()
{
    sudo lxc exec ${@}
}

ci_lxc_exec_user()
{
    ci_lxc_exec --user=1000 --group=1000 ${@}
}

ci_lxc_apt_install()
{
    local lxc_container=$1
    ci_lxc_exec ${lxc_container} -- apt update
    ci_lxc_exec ${lxc_container} -- apt install -y ${@:2}
}

ci_lxc_snap_install()
{
    local lxc_container=$1
    ci_lxc_exec ${lxc_container} -- snap install ${@:2}
}