@Library('juju-pipeline@master') _


pipeline {
    agent {
        label "runner-${params.ARCH}"
    }
    /* XXX: Global $PATH setting doesn't translate properly in pipelines
     https://stackoverflow.com/questions/43987005/jenkins-does-not-recognize-command-sh
     */
    environment {
        PATH                 = "${utils.cipaths}"
        ARCH                 = "${params.ARCH}"
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

    }
    options {
        ansiColor('xterm')
        timestamps()
    }
    stages {
        stage("Setup Tracks") {
            steps {
                script {
                    if (params.ARCH_TRACK == "all") {
                        all_tracks = ["beta", "stable", "pre-release"]
                    } else {
                        all_tracks = [params.ARCH_TRACK.tokenize('/').last()]
                    }
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
        stage("Release Tracks") {
            steps {
                script {
                    all_tracks.each { track -> 
                        stage("Track ${track}") {
                            script {
                                def juju_controller="release-microk8s-${track}-${env.ARCH}"
                                def juju_model="release-microk8s-${track}-model"
                                def juju_full_model="${juju_controller}:${juju_model}"
                                def instance_type = ""
                                def constraints = ""
                                if (env.ARCH == "arm64") {
                                    instance_type = "a1.2xlarge"
                                    constraints = "instance-type=${instance_type} root-disk=80G arch=$ARCH"
                                } else if (env.ARCH == "amd64") {
                                    instance_type = "m5.large"
                                    constraints = "mem=16G cores=8 root-disk=80G arch=$ARCH"
                                } else {
                                    error("Aborting build due to unknown arch=${env.ARCH}")
                                }
                                sh """
                                if ! timeout 4m juju destroy-controller -y --destroy-all-models --destroy-storage "${juju_controller}"; then
                                   timeout 4m juju kill-controller -y "${juju_controller}" || true
                                fi
                                """
                                sh """
                                juju bootstrap "${env.JUJU_CLOUD}" "${juju_controller}" \
                                    -d "${juju_model}" \
                                    --model-default test-mode=true \
                                    --model-default resource-tags=owner=k8sci \
                                    --bootstrap-constraints "instance-type=${instance_type}"

                                juju deploy -m "${juju_full_model}" --constraints "${constraints}" ubuntu

                                juju-wait -e "${juju_full_model}" -w

                                juju ssh -m "${juju_full_model}" --pty=true ubuntu/0 -- 'sudo snap install lxd'
                                juju ssh -m "${juju_full_model}" --pty=true ubuntu/0 -- 'sudo lxd.migrate -yes' || true
                                juju ssh -m "${juju_full_model}" --pty=true ubuntu/0 -- 'sudo lxd init --auto'
                                """
                                if (track == "pre-release"){
                                    sh """
                                    juju ssh -m "${juju_full_model}" --pty=true ubuntu/0 -- 'sudo snap install snapcraft --classic'
                                    """
                                }
                                sh """
                                . .tox/py38/bin/activate
                                DRY_RUN=${params.DRY_RUN} ALWAYS_RELEASE=${params.ALWAYS_RELEASE} \
                                    TESTS_BRANCH=${params.TESTS_BRANCH} TRACKS=${params.TRACKS} \
                                    PROXY=${params.PROXY} JUJU_UNIT=ubuntu/0 \
                                    JUJU_CONTROLLER=${juju_controller} JUJU_MODEL=${juju_model}\
                                    timeout 6h python jobs/microk8s/release-to-${track}.py
                                """
                                sh "juju destroy-controller -y --destroy-all-models --destroy-storage ${juju_controller} || true"
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
                all_tracks.each { track -> 
                    def juju_controller="release-microk8s-${track}-${env.ARCH}"
                    sh "juju destroy-controller -y --destroy-all-models --destroy-storage ${juju_controller} || true"
                }
            }
        }
    }
}
