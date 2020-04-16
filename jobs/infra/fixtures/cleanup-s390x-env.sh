#!/bin/bash -x
for i in $(juju controllers --format json | jq -r '.controllers | keys[]'); do
    if [[ "$i" != "jaas" ]]; then
        echo "$i"
        if ! timeout 2m juju destroy-controller -y --destroy-all-models --destroy-storage "$i"; then
            timeout 2m juju kill-controller -y "$i" 2>&1
        fi
    fi
done
for cntr in $(sudo lxc list --format json | jq -r ".[] | .name"); do
    echo "Removing $cntr"
    sudo lxc delete --force "$cntr"
done

for cntr in $(sudo lxc profile list --format json | jq -r ".[] | .name"); do
    if [[ "$cntr" != "default" ]]; then
        echo "Removing $cntr"
        sudo lxc profile delete "$cntr"
    fi
done
