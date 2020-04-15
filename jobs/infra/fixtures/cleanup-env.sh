#!/bin/bash
set -x

for i in $(juju controllers --format json | jq -r '.controllers | keys[]'); do
    if [ "$i" != "jaas" ]; then
        echo "$i"
        if ! timeout 2m juju destroy-controller -y --destroy-all-models --destroy-storage "$i"; then
            timeout 2m juju kill-controller -y "$i" 2>&1
        fi
    fi
done

sudo apt clean
sudo rm -rf /var/log/*
docker image prune -a --filter until=24h --force
docker container prune --filter until=24h --force
rm -rf /var/lib/jenkins/venvs


for iid in $(aws --region us-east-1 ec2 describe-instances | jq '.Reservations[].Instances[] | select(contains({Tags: [{Key: "owner"} ]}) | not)' | jq -r '.InstanceId'); do
    aws --region us-east-1 ec2 terminate-instances --instance-ids "$iid"
done

for iid in $(aws --region us-east-2 ec2 describe-instances | jq '.Reservations[].Instances[] | select(contains({Tags: [{Key: "owner"} ]}) | not)' | jq -r '.InstanceId'); do
    aws --region us-east-2 ec2 terminate-instances --instance-ids "$iid"
done

for sid in $(aws --region us-east-2 ec2 describe-subnets --query 'Subnets[].SubnetId' --output text); do
    aws --region us-east-2 ec2 delete-tags --resources "$sid" --tags Value=owned
done

for sg in $(aws --region us-east-1 ec2 describe-security-groups --filters Name=owner-id,Values=018302341396 --query "SecurityGroups[*].{Name:GroupId}" --output text); do
    aws --region us-east-1 ec2 delete-security-group --group-id "$sg"
done

for sg in $(aws --region us-east-2 ec2 describe-security-groups --filters Name=owner-id,Values=018302341396 --query "SecurityGroups[*].{Name:GroupId}" --output text); do
    aws --region us-east-2 ec2 delete-security-group --group-id "$sg"
done


for cntr in $(sudo lxc list --format json | jq -r ".[] | .name"); do
    echo "Removing $cntr"
    sudo lxc delete --force "$cntr"
done

for cntr in $(sudo lxc profile list --format json | jq -r ".[] | .name"); do
    if [[ $cntr != "default" ]]; then
	    echo "Removing $cntr"
	    sudo lxc profile delete "$cntr"
    fi
done
