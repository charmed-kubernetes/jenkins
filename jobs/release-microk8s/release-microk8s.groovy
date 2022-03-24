@Library('juju-pipeline@master') _

pipeline {
    agent {
        label "${params.build_node}"
    }
    /* XXX: Global $PATH setting doesn't translate properly in pipelines
     https://stackoverflow.com/questions/43987005/jenkins-does-not-recognize-command-sh
     */
    environment {
        PATH                 = "${utils.cipaths}"
        ARCH                 = "${params.ARCH}"
        DRY_RUN              = "${params.DRY_RUN}"
        ALWAYS_RELEASE       = "${params.ALWAYS_RELEASE}"
        TRACKS               = "${params.TRACKS}"
        TESTS_BRANCH         = "${params.TESTS_BRANCH}"
        PROXY                = "${params.PROXY}"
        ARCH_TRACK           = "${params.ARCH_TRACK}"
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
        stage("Setup Track Tag") {
            steps {
                script {
                    if (env.ARCH_TRACK != "all") {
                        env.all_tracks = ["beta", "stable", "pre-release"]
                    } else {
                        env.all_tracks = [env.ARCH_TRACK.split('/').pop()]
                    }
                }
            }
        }
        stage("Snapcraft login") {
            steps {
                sh "snapcraft login --with ${SNAPCRAFTCREDS}"
            }
        }
        stage("Release Tracks") {
            steps {
                script {
                    env.all_tracks.each { track -> 
                        stages {
                            stage("Setup Track ${track}") {
                                steps {
                                    script {
                                        env.JUJU_CONTROLLER="release-microk8s-${track}-${env.ARCH}"
                                        env.JUJU_MODEL="release-microk8s-${track}-model"
                                        if (env.ARCH == "arm64") {
                                            env.INSTANCE_TYPE = "a1.2xlarge"
                                            env.constraints = "instance-type=${env.INSTANCE_TYPE} arch=$ARCH root-disk=80G"
                                        } else if (env.ARCH == "amd64") {
                                            env.INSTANCE_TYPE = "m5.large"
                                            env.constraints = "instance-type=${env.INSTANCE_TYPE} arch=$ARCH root-disk=80G mem=16G cores=8"
                                        } else {
                                            error("Aborting build due to unknown arch=${env.ARCH}")
                                        }
                                    }
                                    sh """
                                        if ! timeout 2m juju destroy-controller -y --destroy-all-models --destroy-storage "${JUJU_CONTROLLER}"; then
                                        timeout 2m juju kill-controller -y "${JUJU_CONTROLLER}"
                                        fi

                                        juju bootstrap "${JUJU_CLOUD}" "${JUJU_CONTROLLER}" \
                                        -d "${JUJU_MODEL}" \
                                        --model-default test-mode=true \
                                        --model-default resource-tags=owner=k8sci \
                                        --bootstrap-constraints "instance-type=${env.INSTANCE_TYPE}"

                                        juju deploy -m "${JUJU_CONTROLLER}":"${JUJU_MODEL}" --constraints "${env.constraints}" ubuntu

                                        juju-wait -e "${JUJU_CONTROLLER}":"${JUJU_MODEL}" -w

                                        juju ssh -m "${JUJU_CONTROLLER}":"${JUJU_MODEL}" --pty=true ubuntu/0 -- 'sudo snap install lxd'
                                        juju ssh -m "${JUJU_CONTROLLER}":"${JUJU_MODEL}" --pty=true ubuntu/0 -- 'sudo lxd.migrate -yes'
                                        juju ssh -m "${JUJU_CONTROLLER}":"${JUJU_MODEL}" --pty=true ubuntu/0 -- 'sudo lxd init --auto'
                                    """
                                }
                            }
                            stage("Snapcraft Install") {
                                when { expression { track == "pre-release"}}
                                steps {
                                    sh "juju ssh -m "${JUJU_CONTROLLER}":"${JUJU_MODEL}" --pty=true ubuntu/0 -- 'sudo snap install snapcraft --classic'"
                                }
                            }

                            stage("Release") {
                                steps {
                                    sh """
                                        tox -e py38 -- \
                                        DRY_RUN=${DRY_RUN} ALWAYS_RELEASE=${ALWAYS_RELEASE} \
                                        TRACKS=${TRACKS} TESTS_BRANCH=${TESTS_BRANCH} \
                                        PROXY=${PROXY} JUJU_UNIT=ubuntu/0 \
                                        timeout 6h python jobs/microk8s/release-to-${track}.py
                                    """
                                }
                            }
                            post {
                                always {
                                    sh "juju destroy-controller -y --destroy-all-models --destroy-storage ${JUJU_CONTROLLER}"
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}