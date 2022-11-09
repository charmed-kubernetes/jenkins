#!/bin/bash

if [[ $0 == $BASH_SOURCE ]]; then
  echo "$0 should be sourced";
  exit
fi
echo "sourced ${BASH_SOURCE:-$0}"


function purge::az::resources
{
    # Azure groups each juju-model in a resource-group which contains
    # everything allocated for that model. When a resource-group is
    # purged, everything within it is removed
    local user="$1"
    local query="--query=[].[name,tags.owner]"
    local output="--output=tsv"
    echo "Fetching Azure resources..."
    local all_resources=$(az group list $query $output)
    resources=()
    while read -r resource owner; do
        if [[ "$owner" == "$user" ]]; then
            resources+=($resource)
        fi
    done <<< "$all_resources"
    echo -n "Purging Azure resources..."
    if [ -z "$resources" ]; then
        echo "None"
    else
        echo -e "\n$resources\n----"
        for i in "${resources[@]}"; do
            az group delete --resource-group $i -y
        done
    fi
}

function purge::az
{
    local user="k8sci"
    purge::az::resources "$user"
}
