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
    done


    if [[ $(aws iam list-roles --query "length(Roles[?RoleName == 'KubernetesAdmin'])") = *1* ]]
    then
        aws iam delete-role --role-name KubernetesAdmin
    fi

    if [[ $(aws iam list-policies --query "length(Policies[?PolicyName == 'mk8s-ec2-policy'])") = *1* ]]
    then
        POLICY_ARN=$(aws iam list-policies --query "Policies[?PolicyName == 'mk8s-ec2-policy'] | [0].Arn" | tr -d '"')
        if [[ $(aws iam list-roles --query "length(Roles[?RoleName == 'mk8s-ec2-role'])") = *1* ]]
        then
            aws iam detach-role-policy --role-name mk8s-ec2-role --policy-arn $POLICY_ARN
        fi
        aws iam delete-policy --policy-arn $POLICY_ARN
    fi

    if [[ $(aws iam list-instance-profiles --query "length(InstanceProfiles[?InstanceProfileName == 'mk8s-ec2-iprof'])") = *1* ]]
    then
        if [[ $(aws iam list-roles --query "length(Roles[?RoleName == 'mk8s-ec2-role'])") = *1* ]]
        then
            aws iam remove-role-from-instance-profile --instance-profile-name mk8s-ec2-iprof --role-name mk8s-ec2-role
        fi
        aws iam delete-instance-profile --instance-profile-name mk8s-ec2-iprof
    fi

    if [[ $(aws iam list-roles --query "length(Roles[?RoleName == 'mk8s-ec2-role'])") = *1* ]]
    then
        aws iam delete-role --role-name mk8s-ec2-role
    fi

    if [[ $(aws efs describe-file-systems --region us-east-1 --query "length(FileSystems[?Name == 'mk8s-efs'])") = *1* ]]
    then
        EFS_ID=$(aws efs describe-file-systems --region us-east-1 --query "FileSystems[?Name == 'mk8s-efs'] | [0].FileSystemId" --output text)
        if [[ $(aws efs describe-mount-targets --region us-east-1 --file-system-id $EFS_ID --query "length(MountTargets)") = *1* ]]
        then
            MT_ID=$(aws efs describe-mount-targets --region us-east-1 --file-system-id $EFS_ID --query "MountTargets | [0].MountTargetId" --output text)
            aws efs delete-mount-target --region us-east-1 --mount-target-id $MT_ID
        fi
        max_retries=5
        retry=0
        until aws efs delete-file-system --region us-east-1 --file-system-id $EFS_ID
        do
            ((retry++))
            (( retry >= max_retries )) && break
            if [[ $(aws efs describe-mount-targets --region us-east-1 --file-system-id $EFS_ID --query "length(MountTargets)") = *1* ]]
            then
                echo "Waiting 60s for mount target deletion before efs deletion..."
                sleep 60
            else
                break
            fi
        done
    fi

    if [[ $(aws ec2 describe-security-groups --region us-east-1 --query "length(SecurityGroups[?GroupName == 'mk8s-efs-sg'])") = *1* ]]
    then
        aws ec2 delete-security-group --region us-east-1 --group-name mk8s-efs-sg
    fi

    # aws --region us-east-2 ec2 describe-instances | jq '.Reservations[].Instances[] | select(contains({Tags: [{Key: "owner"} ]}) | not)' | jq -r '.InstanceId' | parallel aws --region us-east-2 ec2 terminate-instances --instance-ids {}
    # aws --region us-east-2 ec2 describe-security-groups --filters Name=owner-id,Values=018302341396 --query "SecurityGroups[*].{Name:GroupId}" --output json | jq -r '.[].Name' | parallel aws --region us-east-1 ec2 delete-security-group --group-id "{}"
}