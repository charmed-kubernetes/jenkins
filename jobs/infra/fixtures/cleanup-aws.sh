#!/bin/bash

if [[ $0 == $BASH_SOURCE ]]; then
  echo "$0 should be sourced";
  exit
fi
echo "sourced ${BASH_SOURCE:-$0}"


function purge::aws
{
    default_region=us-east-1

    for region in $(aws --region $default_region ec2 describe-regions | jq -r '.Regions[].RegionName'); do
        echo "Purging AWS $region"
        aws --region "$region" ec2 describe-instances | jq '.Reservations[].Instances[] | select(contains({Tags: [{Key: "owner"} ]}) | not)' | jq -r '.InstanceId' | parallel aws --region "$region" ec2 terminate-instances --instance-ids {}
        aws --region "$region" ec2 describe-instances | jq '.Reservations[].Instances[] | select(contains({Tags: [{Key: "owner", Value: "k8sci"} ]}))' | jq -r '.InstanceId' | parallel aws --region "$region" ec2 terminate-instances --instance-ids {}
        aws --region "$region" ec2 describe-subnets --query 'Subnets[].SubnetId' --output json | jq -r '.[]' | parallel aws --region "$region" ec2 delete-tags --resources {} --tags Value=owned
        aws --region "$region" ec2 describe-security-groups --filters Name=owner-id,Values=018302341396 --query "SecurityGroups[*].{Name:GroupId}" --output json | jq -r '.[].Name' | parallel aws --region "$region" ec2 delete-security-group --group-id "{}"
        aws --region "$region" cloudformation describe-stacks --query "Stacks[?Tags[?Key == 'mk8s']]" | jq -r ".[] | .StackName" | xargs -i aws --region "$region" cloudformation delete-stack --stack-name {}
    done

    # aws --region us-east-2 ec2 describe-instances | jq '.Reservations[].Instances[] | select(contains({Tags: [{Key: "owner"} ]}) | not)' | jq -r '.InstanceId' | parallel aws --region us-east-2 ec2 terminate-instances --instance-ids {}
    # aws --region us-east-2 ec2 describe-security-groups --filters Name=owner-id,Values=018302341396 --query "SecurityGroups[*].{Name:GroupId}" --output json | jq -r '.[].Name' | parallel aws --region us-east-1 ec2 delete-security-group --group-id "{}"
}