#!/bin/bash

if [[ $0 == $BASH_SOURCE ]]; then
  echo "$0 should be sourced";
  exit
fi
echo "sourced ${BASH_SOURCE:-$0}"


function purge::az::instances
{
    local user="$1"
    local query="--query=[].[id,tags.owner]"
    local output="--output=tsv"
    echo "Fetching Azure instances..."
    local all_instances=$(az vm list $query $output)
    instances=()
    while read -r instance owner; do
        if [[ "$owner" == "$user" ]]; then
            instances+=($instance)
        fi
    done <<< "$all_instances"
    echo -n "Purging Azure instances..."
    if [ -z "$instances" ]; then
        echo "None"
    else
        echo -e "\n$instances\n----"
        az vm delete --ids $instances
    fi
}

function purge::az
{
    local user="k8sci"
    purge::az::instances "$user"
}
