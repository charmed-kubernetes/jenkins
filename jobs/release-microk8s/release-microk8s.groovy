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
                                    constraints = "instance-type=${instance_type} root-disk=80G arch=${arch}"
                                } else if (arch == "amd64") {
                                    instance_type = "m5.large"
                                    constraints = "mem=16G cores=8 root-disk=80G arch=${arch}"
                                } else {
                                    error("Aborting build due to unknown arch=${arch}")
                                }
                                sh destroy_controller(juju_controller)
                                sh """
                                juju bootstrap "${JUJU_CLOUD}" "${juju_controller}" \
                                    -d "${juju_model}" \
                                    --model-default test-mode=true \
                                    --model-default resource-tags="owner=k8sci job=${job} stage=${stage}" \
                                    --bootstrap-constraints "instance-type=${instance_type}"

                                juju deploy -m "${juju_full_model}" --constraints "${constraints}" ubuntu

                                juju-wait -e "${juju_full_model}" -w

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
                                             body: 'You can do this. Stay strong!', 
                                             to: env.NOTIFY_EMAIL, 
                                             subject: "${job_name[channel]} completed with errors."
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
