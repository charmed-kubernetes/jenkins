#!/bin/bash
set -x

function purge::controllers
{
    if [ "$1" != "jaas" ]; then
        echo "$1"
        if ! timeout 2m juju destroy-controller -y --destroy-all-models --destroy-storage "$1"; then
            timeout 5m juju kill-controller -y "$1" 2>&1
        fi
    fi
}
export -f purge::controllers

juju controllers --format json | jq -r '.controllers | keys[]' | parallel --ungroup purge::controllers

# for i in $(juju controllers --format json | jq -r '.controllers | keys[]'); do
#     if [ "$i" != "jaas" ]; then
#         echo "$i"
#         if ! timeout 2m juju destroy-controller -y --destroy-all-models --destroy-storage "$i"; then
#             timeout 2m juju kill-controller -y "$i" 2>&1
#         fi
#     fi
# done

sudo apt clean
sudo rm -rf /var/log/*
docker image prune -a --filter until=24h --force
docker container prune --filter until=24h --force
rm -rf /var/lib/jenkins/venvs
rm -rf /var/lib/jenkins/.tox

regions=(us-east-1 us-east-2 us-west-1)

for region in ${regions[@]}; do
    aws --region "$region" ec2 describe-instances | jq '.Reservations[].Instances[] | select(contains({Tags: [{Key: "owner"} ]}) | not)' | jq -r '.InstanceId' | parallel aws --region "$region" ec2 terminate-instances --instance-ids {}
    aws --region "$region" ec2 describe-instances | jq '.Reservations[].Instances[] | select(contains({Tags: [{Key: "owner", Value: "k8sci"} ]}))' | jq -r '.InstanceId' | parallel aws --region "$region" ec2 terminate-instances --instance-ids {}
    aws --region "$region" ec2 describe-subnets --query 'Subnets[].SubnetId' --output json | jq -r '.[]' | parallel aws --region "$region" ec2 delete-tags --resources {} --tags Value=owned
    aws --region "$region" ec2 describe-security-groups --filters Name=owner-id,Values=018302341396 --query "SecurityGroups[*].{Name:GroupId}" --output json | jq -r '.[].Name' | parallel aws --region "$region" ec2 delete-security-group --group-id "{}"
done

# aws --region us-east-2 ec2 describe-instances | jq '.Reservations[].Instances[] | select(contains({Tags: [{Key: "owner"} ]}) | not)' | jq -r '.InstanceId' | parallel aws --region us-east-2 ec2 terminate-instances --instance-ids {}
# aws --region us-east-2 ec2 describe-security-groups --filters Name=owner-id,Values=018302341396 --query "SecurityGroups[*].{Name:GroupId}" --output json | jq -r '.[].Name' | parallel aws --region us-east-1 ec2 delete-security-group --group-id "{}"

sudo lxc list --format json | jq -r ".[] | .name" | parallel sudo lxc delete --force {}
for cntr in $(sudo lxc profile list --format json | jq -r ".[] | .name"); do
    if [[ $cntr != "default" ]]; then
	    echo "Removing $cntr"
	    sudo lxc profile delete "$cntr"
    fi
done
