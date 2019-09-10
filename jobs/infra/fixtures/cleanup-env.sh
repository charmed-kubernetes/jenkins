#!/bin/bash
set -x

for i in $(juju controllers --format json | jq -r '.controllers | keys[]'); do
    echo "$i"
    if ! juju destroy-controller -y --destroy-all-models --destroy-storage "$i" 2>&1; then
        juju kill-controller -y "$i" 2>&1
    fi
done

sudo apt clean
sudo rm -rf /var/log/*
sudo rm -rf /var/lib/jenkins/.cache/*
docker image prune -a --filter until=24h --force
docker container prune --filter until=24h --force
rm -rf /var/lib/jenkins/venvs
rm -rf /var/lib/jenkins/slaves/"$NODE_NAME"/workspace/* 2>&1


for sid in $(aws --region us-east-2 ec2 describe-subnets --query 'Subnets[].SubnetId' --output text); do
    aws --region us-east-2 ec2 delete-tags --resources "$sid" --tags Value=owned
done
