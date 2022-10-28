#!/bin/bash

if [[ $0 == $BASH_SOURCE ]]; then
  echo "$0 should be sourced";
  exit
fi
echo "sourced ${BASH_SOURCE:-$0}"


function purge::gce::instances
{
    local user="$1"
    local fields="--format=table[no-heading](name,zone)"
    local filter="--filter=metadata.items.filter(key:owner).flatten()~$user"
    echo "Fetching GCE instances..."
    local instances=$(gcloud compute instances list $fields $filter)
    echo -n "Purging GCE instances..."
    if [ -z "$instances" ]; then
        echo "None"
    else
        echo -e "\n$instances\n----"
        while read -r host zone; do
            gcloud compute instances delete $host --zone $zone --quiet
        done <<< "$instances"
    fi
}

function purge::gce::service_accounts
{
    local fields="--format=table[no-heading](email)"
    local filter="--filter=email:juju-gcp-"
    echo "Fetching GCE Service Accounts..."
    local service_accounts=$(gcloud iam service-accounts list $fields $filter)
    echo -n "Purging GCE Service Accounts..."
    if [ -z "$service_accounts" ]; then
        echo "None"
    else
        echo -e "\n$service_accounts\n----"
        while read -r email; do
            purge::gce::service_account_keys "$email" "$1"
            gcloud iam service-accounts delete $email --quiet
        done <<< "$service_accounts"
    fi
}

function purge::gce::service_account_keys
{
    local iam="--iam-account=${1}"
    local fields="--format=table[no-heading](name)"
    local filter="--filter=keyType:USER_MANAGED"
    local keys=$(gcloud iam service-accounts keys list $iam $fields $filter)
    echo -n "Purging GCE Service Account Keys for $1 ..."
    if [ -z "$keys" ]; then
        echo "None"
    else
        echo
        while read -r key; do
            gcloud iam service-accounts keys delete $iam $key --quiet
        done <<< "$keys"
    fi    
}

function purge::gce
{
    local user="k8sci"
    gcloud auth activate-service-account --key-file /var/lib/jenkins/.local/share/juju/gce.json
    local project=$(gcloud projects list "--format=table[no-heading](projectId)")
    gcloud config set project "$project"
    purge::gce::service_accounts
    purge::gce::instances "$user"
}
