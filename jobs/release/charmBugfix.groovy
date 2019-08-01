@Library('juju-pipeline@master') _

def release_id = params.release_id
def tracker_sh = "cd jobs && ${utils.cipy} release/release-tracker.py --release-id ${release_id}"

pipeline {
    agent {
        label 'runner'
    }
    environment {
        PATH = "${utils.cipaths}"
    }
    options {
        ansiColor('xterm')
        timestamps()
    }
    stages {
        stage('Build and Promote charms to candidate') {
            when {
                expression {
                    res = sh(returnStdout: true, script: "${tracker_sh} get-phase --name promote-charms").trim()
                    return res != 'pass'
                }
            }
            options {
                timeout(time: 1, unit: 'HOURS')
            }

            steps {
                build job:"build-charms",
                    parameters: [string(name:'charm_branch', value: 'stable'),
                                 string(name:'to_channel', value: params.charm_promote_to)]
                build job:"build-k8s-bundles",
                    parameters: [string(name:'to_channel', value: 'candidate')]
            }
            post {
                failure {
                    sh "${tracker_sh} set-phase --name promote-charms --result fail"
                }
                success {
                    sh "${tracker_sh} set-phase --name promote-charms --result pass"
                }
            }
        }

        stage('Validate: Conformance') {
            when {
                expression {
                    res = sh(returnStdout: true, script: "${tracker_sh} get-phase --name conformance").trim()
                    return res != 'pass'
                }
            }

            options {
                timeout(time: 4, unit: 'HOURS')
            }
            steps {
                build job:"conformance-v${k8sver}.x-canonical-kubernetes",
                    parameters: [string(name:'cloud', value: "google/us-east1"),
                                 string(name:'bundle_channel', value: 'candidate'),
                                 string(name:'version_overlay', value: "jobs/overlays/${k8sver}-candidate-overlay.yaml")]
            }
            post {
                failure {
                    sh "${tracker_sh} set-phase --name conformance --result fail"
                }
                success {
                    sh "${tracker_sh} set-phase --name conformance --result pass"
                }
            }
        }

        stage('Validate') {
            parallel {
                // start e2e
                stage('Validate: e2e') {
                    when {
                        expression {
                            res = sh(returnStdout: true, script: "${tracker_sh} get-phase --name validate").trim()
                            return res != 'pass'
                        }
                    }

                    options {
                        timeout(time: 4, unit: 'HOURS')
                    }

                    steps {
                        build job:"validate-v${k8sver}.x-canonical-kubernetes",
                            parameters: [string(name:'cloud', value: "aws/us-east-1"),
                                         string(name:'bundle_channel', value:'candidate'),
                                         string(name:'snap_channel', value:"${k8sver}/candidate"),
                                         string(name:'version_overlay', value: "jobs/overlays/${k8sver}-candidate-overlay.yaml")]
                    }
                    post {
                        failure {
                            sh "${tracker_sh} set-phase --name validate --result fail"
                        }
                        success {
                            sh "${tracker_sh} set-phase --name validate --result pass"
                        }
                    }
                }
                // end e2e

                // start minor upgrade
                stage('Validate: Minor Upgrades') {
                    when {
                        expression {
                            res = sh(returnStdout: true, script: "${tracker_sh} get-phase --name validate-upgrade").trim()
                            return res != 'pass'
                        }
                    }

                    options {
                        timeout(time: 4, unit: 'HOURS')
                    }
                    steps {
                        build job:"validate-minor-upgrade-${k8sver_range}",
                            parameters: [string(name:'cloud', value: "google/us-east1"),
                                         string(name:'upgrade_snap_channel', value:"${k8sver}/candidate"),
                                         string(name:'bundle_channel', value:"candidate"),
                                         string(name:'upgrade_charm_channel', value:"candidate")]

                    }
                    post {
                        failure {
                            sh "${tracker_sh} set-phase --name validate-upgrade --result fail"
                        }
                        success {
                            sh "${tracker_sh} set-phase --name validate-upgrade --result pass"
                        }
                    }
                }
                // end minor upgrade
            }
        }


        stage('Validate: Addons') {
            parallel {
                // start vault
                stage('Validate: Vault') {
                    when {
                        expression {
                            res = sh(returnStdout: true, script: "${tracker_sh} get-phase --name validate-vault").trim()
                            return res != 'pass'
                        }
                    }

                    options {
                        timeout(time: 4, unit: 'HOURS')
                    }
                    steps {
                        build job:"validate-vault-v${k8sver}.x",
                            parameters: [string(name:'cloud', value: "google/us-east1"),
                                         string(name:'controller', value: "release-vault"),
                                         string(name:'bundle_channel', value:"candidate"),
                                         string(name:'bundle', value:"canonical-kubernetes"),
                                         string(name:'overlay', value: "jobs/overlays/${k8sver}-candidate-overlay.yaml")]

                    }
                    post {
                        failure {
                            sh "${tracker_sh} set-phase --name validate-vault --result fail"
                        }
                        success {
                            sh "${tracker_sh} set-phase --name validate-vault --result pass"
                        }
                    }
                }
                // end vault

                // start nvidia
                stage('Validate: NVidia') {
                    when {
                        expression {
                            res = sh(returnStdout: true, script: "${tracker_sh} get-phase --name validate-nvidia").trim()
                            return res != 'pass'
                        }
                    }

                    options {
                        timeout(time: 4, unit: 'HOURS')
                    }
                    steps {
                        build job:"validate-nvidia-v${k8sver}.x",
                            parameters: [string(name:'cloud', value: "aws/us-east-1"),
                                         string(name:'bundle_channel', value:"candidate"),
                                         string(name:'controller', value:"release-nvidia"),
                                         string(name:'overlay', value: "jobs/overlays/${k8sver}-candidate-overlay.yaml")]

                    }
                    post {
                        failure {
                            sh "${tracker_sh} set-phase --name validate-nvidia --result fail"
                        }
                        success {
                            sh "${tracker_sh} set-phase --name validate-nvidia --result pass"
                        }
                    }
                }
                // end nvidia

                // start calico
                stage('Validate: Calico') {
                    when {
                        expression {
                            res = sh(returnStdout: true, script: "${tracker_sh} get-phase --name validate-calico").trim()
                            return res != 'pass'
                        }
                    }

                    options {
                        timeout(time: 4, unit: 'HOURS')
                    }
                    steps {
                        build job:"validate-calico-v${k8sver}.x",
                            parameters: [string(name:'controller', value:"release-calico"),
                                         string(name:'bundle_channel', value:"candidate"),
                                         string(name:'overlay', value: "jobs/overlays/${k8sver}-candidate-overlay.yaml")]

                    }
                    post {
                        failure {
                            sh "${tracker_sh} set-phase --name validate-calico --result fail"
                        }
                        success {
                            sh "${tracker_sh} set-phase --name validate-calico --result pass"
                        }
                    }
                }
                // end calico

                // start tigera
                stage('Validate: Tigera') {
                    when {
                        expression {
                            res = sh(returnStdout: true, script: "${tracker_sh} get-phase --name validate-tigera").trim()
                            return res != 'pass'
                        }
                    }

                    options {
                        timeout(time: 4, unit: 'HOURS')
                    }
                    steps {
                        build job:"validate-tigera-secure-ee-v${k8sver}.x",
                            parameters: [string(name:'bundle_channel', value:"candidate"),
                                         string(name:'controller', value:'release-tigera'),
                                         string(name:'overlay', value: "jobs/overlays/${k8sver}-candidate-overlay.yaml")]

                    }
                    post {
                        failure {
                            sh "${tracker_sh} set-phase --name validate-tigera --result fail"
                        }
                        success {
                            sh "${tracker_sh} set-phase --name validate-tigera --result pass"
                        }
                    }
                }
                // end tigera
            }
        }

        stage('Validate: Localhost and Alternate Arches') {
            when {
                expression {
                    res = sh(returnStdout: true, script: "${tracker_sh} get-phase --name validate-alt").trim()
                    return res != 'pass'
                }
            }

            options {
                timeout(time: 5, unit: 'HOURS')
            }
            steps {
                script {
                    def jobs = [:]
                    def arches = ['amd64', 'arm64', 'ppc64le', 's390x']
                    arches.each { arch ->
                        jobs[arch] = {
                            stage(String.format("Validate arch: %s", arch)) {
                                build job:"validate-alt-${arch}-v${k8sver}.x-canonical-kubernetes",
                                    parameters: [string(name:'bundle_channel', value:'candidate'),
                                                 string(name:'snap_channel', value:"${k8sver}/candidate"),
                                                 string(name:'version_overlay', value: "jobs/overlays/${k8sver}-candidate-overlay.yaml")]

                            }
                        }
                    }
                    parallel jobs
                }
            }
            post {
                failure {
                    sh "${tracker_sh} set-phase --name validate-alt --result fail"
                }
                success {
                    sh "${tracker_sh} set-phase --name validate-alt --result pass"
                }
            }

        }
    }
}
