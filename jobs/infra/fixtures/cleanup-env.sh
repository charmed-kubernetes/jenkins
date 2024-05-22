#!/bin/bash
set -x

THISDIR="$(dirname "$(realpath "$0")")"
. "$THISDIR/cleanup-aws.sh"  # import AWS methods
. "$THISDIR/cleanup-gce.sh"  # import GCE methods
. "$THISDIR/cleanup-az.sh"   # import Azure methods


function purge::controllers
{
    if [ "$1" != "jaas" ]; then
        echo "$1"
        if ! timeout 2m juju destroy-controller --no-prompt --destroy-all-models --destroy-storage "$1"; then
            timeout 5m juju kill-controller -t 2m0s --no-prompt "$1" 2>&1
        fi
    fi
}
export -f purge::controllers

juju controllers --format json | jq -r '.controllers | keys[]' | parallel --ungroup purge::controllers

# for i in $(juju controllers --format json | jq -r '.controllers | keys[]'); do
#     if [ "$i" != "jaas" ]; then
#         echo "$i"
#         if ! timeout 2m juju destroy-controller --no-prompt --destroy-all-models --destroy-storage "$i"; then
#             timeout 2m juju kill-controller --no-prompt "$i" 2>&1
#         fi
#     fi
# done

sudo apt clean
docker image prune -a --filter until=24h --force
docker container prune --filter until=24h --force
rm -rf /var/lib/jenkins/venvs
rm -rf /var/lib/jenkins/.tox
sudo tmpreaper 5h /tmp

purge::aws
purge::gce
purge::az

sudo lxc list --format json | jq -r ".[] | .name" | parallel sudo lxc delete --force {}
for cntr in $(sudo lxc profile list --format json | jq -r ".[] | .name"); do
    if [[ $cntr != "default" ]]; then
	    echo "Removing $cntr"
	    sudo lxc profile delete "$cntr"
    fi
done
