@Library('juju-pipeline@master') _


def destroy_controller(controller) {
    return """#!/bin/bash
    if ! timeout 4m juju destroy-controller -y --destroy-all-models --destroy-storage "${controller}"; then
        timeout 4m juju kill-controller -y "${controller}" || true
    fi

    if [[ \$(aws --region us-east-1 cloudformation describe-stacks --query "length(Stacks[?StackName == '${controller}'])") = *1* ]]
    then
        aws cloudformation delete-stack --stack-name ${controller} --region us-east-1 || true
    fi
    """
}

def setup_lxc() {
    return """#!/usr/bin/env bash
    . \$WORKSPACE/lxc_runner.sh
    ci_lxc_init_runner _lxc notrap 1>&2
    echo \${_lxc}
    """
}

def delete_lxc(container_name) {
    return """#!/usr/bin/env bash
    . \${WORKSPACE}/cilib.sh

    ci_lxc_delete ${container_name}
    """
}

def run_lxc(container_name, command) {
    return """#!/usr/bin/env bash
    . \$WORKSPACE/lxc_runner.sh

    _job_sh=\$(basename \$(mktemp -p \$WORKSPACE --suffix=.sh))

    # push job script into workspace and run
    cat << 'EOF' > \$WORKSPACE/\$_job_sh

    #!/bin/bash
    set -eux
    set -o allexport
    [[ -f \$WORKSPACE/.env ]] && source \$WORKSPACE/.env
    set +o allexport

    ${command}
    EOF
    ci_lxc_job_run ${container_name} -- bash \$LXC_WORKSPACE/\$_job_sh
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
        LXC_APT_LIST         = "awscli,pip,python3-venv,python3-dev,libffi-dev"
        LXC_SNAP_LIST        = "juju --channel=3.1,juju-wait,juju-crashdump,snapcraft"
        LXC_PUSH_LIST        = "${SNAPCRAFTCREDS}"
        LXC_MOUNT_LIST       = ".local,.ssh,.aws,.config"

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
        stage("Setup LXC") {
            steps {
                lxc_name = sh (script: setup_lxc, returnStdout: true).trim()
            }
        }
        stage("Snapcraft login") {
            steps {
                sh "snapcraft login --with ${SNAPCRAFTCREDS}"
            }
        }
        stage("Setup tox environment") {
            steps {
                sh run_lxc(lxc_name, """
                tox -e py38 -- python -c 'print("Tox Environment Ready")'
                """)
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
                                def eksd_instance_type = ""
                                def constraints = ""
                                def job_name = [
                                    beta: "release-to-beta.py",
                                    stable: "release-to-stable.py",
                                    "pre-release": "release-pre-release.py",
                                ]

                                try {
                                    sh """
                                    . .tox/py38/bin/activate
                                    ALWAYS_RELEASE=${params.ALWAYS_RELEASE}\
                                        TRACKS=${params.TRACKS}\
                                        CHANNEL=${channel}\
                                        timeout 6h python jobs/microk8s/release-needed.py
                                    """
                                } catch (err) {
                                    return 0
                                }

                                if (arch == "arm64") {
                                    constraints = "mem=16G cores=8 root-disk=80G arch=${arch}"
                                    eksd_instance_type = "m6g.large"
                                } else if (arch == "amd64") {
                                    if ("${channel}" == "stable") {
                                        constraints = "instance-type=g3s.xlarge root-disk=80G arch=${arch}"
                                    } else {
                                        constraints = "mem=16G cores=8 root-disk=80G arch=${arch}"
                                    }
                                    eksd_instance_type = "m4.large"
                                } else {
                                    error("Aborting build due to unknown arch=${arch}")
                                }
                                sh run_lxc(lxc_name, destroy_controller(juju_controller))
                                sh run_lxc(lxc_name, """
                                    juju bootstrap "${JUJU_CLOUD}" "${juju_controller}" \
                                    --add-model "${juju_model}" \
                                    --model-default test-mode=true \
                                    --model-default resource-tags="owner=k8sci job=${job} stage=${stage}" \
                                    --bootstrap-constraints "mem=8G cores=2"

                                    juju deploy -m "${juju_full_model}" --constraints "${constraints}" ubuntu
                                    juju-wait -e "${juju_full_model}" -w

                                    set +x
                                    AWS_ACCESS_KEY_ID=\$(aws configure get aws_access_key_id)
                                    AWS_SECRET_ACCESS_KEY=\$(aws configure get aws_secret_access_key)

                                    juju ssh -m "${juju_full_model}" --pty=true ubuntu/0 -- "sudo echo INSTANCE_TYPE=${eksd_instance_type} | sudo tee -a /etc/environment"
                                    juju ssh -m "${juju_full_model}" --pty=true ubuntu/0 -- "sudo echo STACK_NAME=${juju_controller} | sudo tee -a /etc/environment"
                                    juju ssh -m "${juju_full_model}" --pty=true ubuntu/0 -- "sudo echo AWS_REGION=\$AWS_REGION | sudo tee -a /etc/environment"
                                    juju ssh -m "${juju_full_model}" --pty=true ubuntu/0 -- "sudo echo AWS_ACCESS_KEY_ID=\$AWS_ACCESS_KEY_ID | sudo tee -a /etc/environment"
                                    juju ssh -m "${juju_full_model}" --pty=true ubuntu/0 -- "sudo echo AWS_SECRET_ACCESS_KEY=\$AWS_SECRET_ACCESS_KEY | sudo tee -a /etc/environment"
                                    set -x

                                    juju ssh -m "${juju_full_model}" --pty=true ubuntu/0 -- 'sudo snap install lxd'
                                    juju ssh -m "${juju_full_model}" --pty=true ubuntu/0 -- 'sudo lxd.migrate -yes' || true
                                    juju ssh -m "${juju_full_model}" --pty=true ubuntu/0 -- 'sudo lxd init --auto'
                                    """
                                )
                                if (channel == "pre-release"){
                                    sh run_lxc(lxc_name, """
                                        juju ssh -m "${juju_full_model}" --pty=true ubuntu/0 -- 'sudo snap install snapcraft --classic'
                                    """)
                                }

                                try {
                                    sh run_lxc(lxc_name, """
                                    . .tox/py38/bin/activate
                                    DRY_RUN=${params.DRY_RUN} ALWAYS_RELEASE=${params.ALWAYS_RELEASE}\
                                        TESTS_BRANCH=${params.TESTS_BRANCH} TRACKS=${params.TRACKS}\
                                        PROXY=${params.PROXY} JUJU_UNIT=ubuntu/0\
                                        JUJU_CONTROLLER=${juju_controller} JUJU_MODEL=${juju_model}\
                                        timeout 6h python jobs/microk8s/${job_name[channel]}
                                    """)
                                } catch (err) {
                                    unstable("${job_name[channel]} completed with errors.")
                                    emailext(
                                             to: env.NOTIFY_EMAIL,
                                             subject: "Job '${JOB_NAME}' (${BUILD_NUMBER}) had an on stage ${job_name[channel]}",
                                             body: "Please go to ${BUILD_URL} and verify the build"
                                    )
                                } finally {
                                    sh run_lxc(lxc_name, destroy_controller(juju_controller))
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
                        sh run_lxc(lxc_name, destroy_controller(juju_controller))
                    }
                }
                sh delete_lxc(lxc_name)
            }
        }
    }
}
