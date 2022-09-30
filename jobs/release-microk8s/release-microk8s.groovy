@Library('juju-pipeline@master') _


def destroy_controller(controller) {
    return """
    if ! timeout 4m juju destroy-controller -y --destroy-all-models --destroy-storage "${controller}"; then
        timeout 4m juju kill-controller -y "${controller}" || true
    fi
    """
}

pipeline {
    agent {
        label "runner-${params.ARCH}"
    }
    /* XXX: Global $PATH setting doesn't translate properly in pipelines
     https://stackoverflow.com/questions/43987005/jenkins-does-not-recognize-command-sh
     */
    environment {
        PATH                 = "${utils.cipaths}"
        AWS_REGION           = "us-east-1"
        JUJU_CLOUD           = "aws/us-east-1"
        K8STEAMCI            = credentials('k8s_team_ci_lp')
        CDKBOT_GH            = credentials('cdkbot_github')
        LPCREDS              = credentials('launchpad_creds')
        CHARM_CREDS          = credentials('charm_creds')
        JUJU_CREDS           = credentials('juju_creds')
        JUJU_CLOUDS          = credentials('juju_clouds')
        SSOCREDS             = credentials('sso_token')
        SNAPCRAFTCREDS       = credentials('snapcraft_creds')
        SNAPCRAFTCPCCREDS    = credentials('snapcraft_cpc_creds')
        AWS_CREDS            = credentials('aws_creds')
        SURL_CREDS           = credentials('surl-creds')
        AWSIAMARN            = credentials('aws-iam-arn')
        CDKBOTSSHCREDS       = credentials('cdkbot_ssh_rsa')
        K8STEAMCI_GPG_PUB    = credentials('deb-gpg-public')
        K8STEAMCI_GPG_PRIVATE= credentials('deb-gpg-private')
        K8STEAMCI_GPG_KEY    = credentials('deb-gpg-key')
        NOTIFY_EMAIL         = credentials('microk8s_notify_email')

    }
    options {
        ansiColor('xterm')
        timestamps()
    }
    stages {
        stage("Setup Channels") {
            steps {
                script {
                    arch = params.ARCH
                    channels = ["beta", "stable", "pre-release"].findAll { channel ->
                        params.CHANNEL == "all" || params.CHANNEL == channel
                    }
                    echo "Running for channels ${arch}/${channels}"
                }
            }
        }
        stage("Snapcraft login") {
            steps {
                sh "snapcraft login --with ${SNAPCRAFTCREDS}"
            }
        }
        stage("Setup tox environment") {
            steps {
                sh """
                tox -e py38 -- python -c 'print("Tox Environment Ready")'
                """
            }
        }
        stage("Run Release Steps") {
            steps {
                script {
                    channels.each { channel -> 
                        stage("Channel ${channel}") {
                            script {
                                def job="release-microk8s"
                                def stage="${channel}-${arch}"
                                def juju_controller="${job}-${stage}"
                                def juju_model="${job}-${stage}-model"
                                def juju_full_model="${juju_controller}:${juju_model}"
                                def instance_type = ""
                                def constraints = ""
                                def job_name = [
                                    beta: "release-to-beta.py",
                                    stable: "release-to-stable.py",
                                    "pre-release": "release-pre-release.py",
                                ]

                                if (arch == "arm64") {
                                    instance_type = "a1.2xlarge"
                                    constraints = "instance-type=${instance_type} root-disk=80G arch=${arch} instance-role=mk8s-ec2-iprof"
                                } else if (arch == "amd64") {
                                    instance_type = "m5.large"
                                    constraints = "mem=16G cores=8 root-disk=80G arch=${arch} instance-role=mk8s-ec2-iprof"
                                } else {
                                    error("Aborting build due to unknown arch=${arch}")
                                }
                                sh destroy_controller(juju_controller)
                                sh """#!/bin/bash -xe
                                POLICY=\$(echo -n '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Action":["elasticfilesystem:DescribeAccessPoints","elasticfilesystem:DescribeFileSystems","elasticfilesystem:DescribeMountTargets","ec2:DescribeAvailabilityZones"],"Resource":"*"},{"Effect":"Allow","Action":["elasticfilesystem:CreateAccessPoint"],"Resource":"*","Condition":{"StringLike":{"aws:RequestTag/efs.csi.aws.com/cluster":"true"}}},{"Effect":"Allow","Action":"elasticfilesystem:DeleteAccessPoint","Resource":"*","Condition":{"StringEquals":{"aws:ResourceTag/efs.csi.aws.com/cluster":"true"}}}]}')
                                ROLE_POLICY=\$(echo -n '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"ec2.amazonaws.com"},"Action":"sts:AssumeRole"}]}')
                                
                                if [[ \$(aws iam list-policies --query "length(Policies[?PolicyName == 'mk8s-ec2-policy'])") = *0* ]]
                                then
                                    POLICY_ARN=\$(aws iam create-policy --policy-name mk8s-ec2-policy --policy-document "\$POLICY" --query "Policy.Arn" --output text)
                                else
                                    POLICY_ARN=\$(aws iam list-policies --query "Policies[?PolicyName == 'mk8s-ec2-policy'] | [0].Arn" | tr -d '"')
                                fi

                                if [[ \$(aws iam list-roles --query "length(Roles[?RoleName == 'mk8s-ec2-role'])") = *0* ]]
                                then
                                    aws iam create-role --role-name mk8s-ec2-role --assume-role-policy-document "\$ROLE_POLICY" --description "Kubernetes administrator role (for AWS IAM Authenticator for Kubernetes)."
                                    aws iam attach-role-policy --role-name mk8s-ec2-role --policy-arn \$POLICY_ARN
                                fi

                                if [[ \$(aws iam list-instance-profiles --query "length(InstanceProfiles[?InstanceProfileName == 'mk8s-ec2-iprof'])") = *0* ]]
                                then
                                    aws iam create-instance-profile --instance-profile-name mk8s-ec2-iprof
                                    aws iam add-role-to-instance-profile --instance-profile-name mk8s-ec2-iprof --role-name mk8s-ec2-role
                                fi

                                juju bootstrap "${JUJU_CLOUD}" "${juju_controller}" \
                                    -d "${juju_model}" \
                                    --model-default test-mode=true \
                                    --model-default resource-tags="owner=k8sci job=${job} stage=${stage}" \
                                    --bootstrap-constraints "instance-type=${instance_type}"

                                juju deploy -m "${juju_full_model}" --constraints "${constraints}" ubuntu

                                juju-wait -e "${juju_full_model}" -w

                                INSTANCE_ID=\$(juju show-machine 0 --format json | jq '.machines."0"."instance-id"' | tr -d '"')
                                AVAILABILITY_ZONE=\$(aws ec2 describe-instances --region "${AWS_REGION}" --instance-id \$INSTANCE_ID --query "Reservations | [0].Instances | [0].Placement.AvailabilityZone" --output text)
                                SUBNET_ID=\$(aws ec2 describe-instances --region "${AWS_REGION}" --instance-id \$INSTANCE_ID --query "Reservations | [0].Instances | [0].SubnetId" --output text)

                                if [[ \$(aws ec2 describe-security-groups --region "${AWS_REGION}" --query "length(SecurityGroups[?GroupName == 'mk8s-efs-sg'])") = *0* ]]
                                then
                                    SG_ID=\$(aws ec2 create-security-group --region "${AWS_REGION}" --group-name mk8s-efs-sg --description "MicroK8s EFS testing security group" --query "GroupId" --output text)
                                    aws ec2 authorize-security-group-ingress --region "${AWS_REGION}" --group-id \$SG_ID --protocol tcp --port 2049 --cidr 0.0.0.0/0
                                else
                                    SG_ID=\$(aws ec2 describe-security-groups --region "${AWS_REGION}" --query "SecurityGroups[?GroupName == 'mk8s-efs-sg'] | [0].GroupId" --output text)
                                fi

                                if [[ \$(aws efs describe-file-systems --region "${AWS_REGION}" --query "length(FileSystems[?Name == 'mk8s-efs'])") = *0* ]]
                                then
                                    export EFS_ID=\$(aws efs create-file-system --region "${AWS_REGION}" --encrypted --creation-token mk8stestingefs --tags Key=Name,Value=mk8s-efs --availability-zone-name \$AVAILABILITY_ZONE --query "FileSystemId" --output text)
                                else
                                    export EFS_ID=\$(aws efs describe-file-systems --region "${AWS_REGION}" --query "FileSystems[?Name == 'mk8s-efs'] | [0].FileSystemId" --output text)
                                fi

                                if [[ \$(aws efs describe-mount-targets --region "${AWS_REGION}" --file-system-id \$EFS_ID --query "length(MountTargets)") = *0* ]]
                                then
                                    max_retries=5
                                    retry=0
                                    until aws efs create-mount-target --region "${AWS_REGION}" --file-system-id \$EFS_ID --subnet-id \$SUBNET_ID --security-group \$SG_ID
                                    do
                                        ((n++))
                                        (( n >= max_retries )) && break
                                        echo "Retrying creating mount target for EFS..."
                                        sleep 10
                                    done
                                else
                                    if [[ \$(aws efs describe-mount-targets --region "${AWS_REGION}" --file-system-id \$EFS_ID --query "MountTargets | [0].AvailabilityZoneName") != *\$AVAILABILITY_ZONE* ]]
                                    then
                                        MT_ID=\$(aws efs describe-mount-targets --region "${AWS_REGION}" --file-system-id \$EFS_ID --query "MountTargets | [0].MountTargetId")
                                        aws efs delete-mount-target --region "${AWS_REGION}" --mount-target-id \$MT_ID
                                        max_retries=5
                                        retry=0
                                        until aws efs create-mount-target --region "${AWS_REGION}" --file-system-id \$EFS_ID --subnet-id \$SUBNET_ID --security-group \$SG_ID
                                        do
                                            ((n++))
                                            (( n >= max_retries )) && break
                                            echo "Retrying creating mount target for EFS..."
                                            sleep 10
                                        done
                                    fi
                                fi

                                if [[ \$(aws iam list-roles --query "length(Roles[?RoleName == 'KubernetesAdmin'])") = *0* ]]
                                then
                                    ACCOUNT_ID=\$(aws sts get-caller-identity --query 'Account' --output text)
                                    POLICY=\$(echo -n '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"AWS":"arn:aws:iam::'; echo -n "\$ACCOUNT_ID"; echo -n ':root"},"Action":"sts:AssumeRole","Condition":{}}]}')
                                    KUBERNETES_ADMIN_ARN=\$(aws iam create-role --role-name KubernetesAdmin --description "Kubernetes administrator role (for AWS IAM Authenticator for Kubernetes)." --assume-role-policy-document "\$POLICY" --output text --query 'Role.Arn')
                                else
                                    KUBERNETES_ADMIN_ARN=\$(aws iam list-roles --query "Roles[?RoleName == 'KubernetesAdmin'] | [0].Arn" --output text)
                                fi

                                AWS_ACCESS_KEY_ID=\$(aws configure get aws_access_key_id)
                                AWS_SECRET_ACCESS_KEY=\$(aws configure get aws_secret_access_key)

                                juju run --unit ubuntu/0 "open-port 2049"
                                juju expose ubuntu

                                juju ssh -m "${juju_full_model}" --pty=true ubuntu/0 -- 'export EFS_ID=\$EFS_ID'
                                juju ssh -m "${juju_full_model}" --pty=true ubuntu/0 -- 'export KUBERNETES_ADMIN_ARN=\$KUBERNETES_ADMIN_ARN'
                                juju ssh -m "${juju_full_model}" --pty=true ubuntu/0 -- 'export AWS_ACCESS_KEY_ID=\$AWS_ACCESS_KEY_ID'
                                juju ssh -m "${juju_full_model}" --pty=true ubuntu/0 -- 'export AWS_SECRET_ACCESS_KEY=\$AWS_SECRET_ACCESS_KEY'


                                juju ssh -m "${juju_full_model}" --pty=true ubuntu/0 -- 'sudo snap install lxd'
                                juju ssh -m "${juju_full_model}" --pty=true ubuntu/0 -- 'sudo lxd.migrate -yes' || true
                                juju ssh -m "${juju_full_model}" --pty=true ubuntu/0 -- 'sudo lxd init --auto'
                                """
                                if (channel == "pre-release"){
                                    sh """
                                    juju ssh -m "${juju_full_model}" --pty=true ubuntu/0 -- 'sudo snap install snapcraft --classic'
                                    """
                                }
                                try {
                                    sh """
                                    . .tox/py38/bin/activate
                                    DRY_RUN=${params.DRY_RUN} ALWAYS_RELEASE=${params.ALWAYS_RELEASE}\
                                        TESTS_BRANCH=${params.TESTS_BRANCH} TRACKS=${params.TRACKS}\
                                        PROXY=${params.PROXY} JUJU_UNIT=ubuntu/0\
                                        JUJU_CONTROLLER=${juju_controller} JUJU_MODEL=${juju_model}\
                                        timeout 6h python jobs/microk8s/${job_name[channel]}
                                    """
                                } catch (err) {
                                    unstable("${job_name[channel]} completed with errors.")
                                    emailext(
                                             to: env.NOTIFY_EMAIL,
                                             subject: "Job '${JOB_NAME}' (${BUILD_NUMBER}) had an on stage ${job_name[channel]}",
                                             body: "Please go to ${BUILD_URL} and verify the build"
                                    )
                                } finally {
                                    sh destroy_controller(juju_controller)
                                }
                            }
                        }
                    }
                }
            }
        }
    }
    post {
        always {
            script {
                if (getBinding().hasVariable("channels")) {
                    channels.each { channel -> 
                        def job="release-microk8s"
                        def stage="${channel}-${arch}"
                        def juju_controller="${job}-${stage}"
                        sh destroy_controller(juju_controller)
                    }
                }
            }
        }
    }
}
