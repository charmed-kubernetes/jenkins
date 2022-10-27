#!/bin/bash

if [[ $0 == $BASH_SOURCE ]]; then
  echo "$0 should be sourced";
  exit
fi
echo "sourced ${BASH_SOURCE:-$0}"


function purge:gce:instances
{
    local user="$1"
    local project="--project=$2"
    local fields="--format=table[no-heading](name,zone)"
    local filter="--filter=metadata.items.filter(key:owner).flatten()~$user"
    echo "Fetching GCE instances..."
    local instances=$(gcloud compute instances list $project $fields $filter)
    echo -n "Purging GCE instances..."
    if [ -z "$instances" ]; then
        echo "None"
    else
        echo -e "\n$instances\n----"
        while read -r host zone; do
            echo gcloud compute instances delete $host --zone $zone $project --quiet
        done <<< "$instances"
    fi
}

function purge:gce:service_accounts
{
    local project="--project=${1}"
    local fields="--format=table[no-heading](email)"
    local filter="--filter=email:juju-gcp-"
    echo "Fetching GCE Service Accounts..."
    local service_accounts=$(gcloud iam service-accounts list $project $fields $filter)
    echo -n "Purging GCE Service Accounts..."
    if [ -z "$service_accounts" ]; then
        echo "None"
    else
        echo -e "\n$service_accounts\n----"
        while read -r email; do
            purge:gce:service_account_keys "$email" "$1"
            gcloud iam service-accounts delete $email $project --quiet
        done <<< "$service_accounts"
    fi
}

function purge:gce:service_account_keys
{
    local iam="--iam-account=${1}"
    local project="--project=${2}"
    local fields="--format=table[no-heading](name)"
    local filter="--filter=keyType:USER_MANAGED"
    local keys=$(gcloud iam service-accounts keys list $project $iam $fields $filter)
    echo -n "Purging GCE Service Account Keys for $1 ..."
    if [ -z "$keys" ]; then
        echo "None"
    else
        echo
        while read -r key; do
            gcloud iam service-accounts keys delete $project $iam $key --quiet
        done <<< "$keys"
    fi    
}

function purge:gce
{
    local project="ubuntu-benchmarking"
    purge:gce:service_accounts $project
    purge:gce:instances k8sci $project
}
