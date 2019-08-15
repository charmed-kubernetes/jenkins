@Library('juju-pipeline@master') _

def juju_model = String.format("%s-%s", params.model, uuid())
def juju_controller = String.format("%s-%s", params.controller, uuid())
def charm_sh = "${utils.cibin}/ogc"

pipeline {
    agent { label 'runner-amd64' }
    /* XXX: Global $PATH setting doesn't translate properly in pipelines
     https://stackoverflow.com/questions/43987005/jenkins-does-not-recognize-command-sh
     */
    environment {
        PATH = "${utils.cipaths}"
        CHARM_BUILD_DIR = "${env.WORKSPACE}/build/charms"
        CHARM_LAYERS_DIR = "${env.WORKSPACE}/build/layers"
        CHARM_INTERFACES_DIR = "${env.WORKSPACE}/build/interfaces"
        TMPDIR = "${env.WORKSPACE}/tmp"
    }
    options {
        ansiColor('xterm')
        timestamps()
    }
    stages {
        stage('Setup') {
            steps {
                // setStartTime()
                sh "rm -rf ${env.CHARM_BUILD_DIR} && mkdir -p ${env.CHARM_BUILD_DIR}"
                sh "rm -rf ${env.CHARM_LAYERS_DIR} && mkdir -p ${env.CHARM_LAYERS_DIR}"
                sh "rm -rf ${env.CHARM_INTERFACES_DIR} && mkdir -p ${env.CHARM_INTERFACES_DIR}"
                sh "mkdir -p ${env.TMPDIR}"
            }
        }
        stage('Build, Push, Promote Charms') {
            options {
                timeout(time: 90, unit: 'MINUTES')
            }
            steps {
                dir('jobs') {
                    sh "CHARM_CACHE_DIR=${env.TMPDIR}/.charm ${charm_sh} charm build --charm-list includes/charm-support-matrix.inc --charm-branch ${params.charm_branch} --to-channel ${params.to_channel} --resource-spec build-charms/resource-spec.yaml --filter-by-tag ${params.tag} --layer-index ${params.layer_index} --layer-list includes/charm-layer-list.inc --layer-branch ${params.layer_branch}"
                    sh "CHARM_CACHE_DIR=${env.TMPDIR}/.charm ${charm_sh} charm build-bundles --to-channel ${params.to_channel} --filter-by-tag ${params.tag} --bundle-list includes/charm-bundles-list.inc"
                }
            }
        }
    }
    post {
        // failure {
        //     setFail()
        // }
        // success {
        //     setPass()
        // }
        cleanup {
            // saveMeta()
            // collectDebug(juju_controller, juju_model)
            tearDown(juju_controller)
        }
    }
}

        // stage('Test') {
        //     options {
        //         timeout(time: 2, unit: 'HOURS')
        //     }

        //     steps {
        //         dir("jobs") {
        //             script {
        //                 def test_path = "integration/charm/test_${params.charm}.py"
        //                 if (fileExists(test_path)) {
        //                     sh "juju bootstrap ${params.cloud} ${juju_controller} --debug"
        //                     sh "CHARM_PATH=${env.CHARM_BUILD_DIR}/${params.charm} CONTROLLER=${juju_controller} MODEL=${juju_model} CLOUD=${params.cloud} ${utils.pytest} -n auto --junit-xml=${params.charm}.xml ${test_path}"
        //                 }
        //             }

        //         }
        //     }
        //     post {
        //         always {
        //             setEndTime()
        //         }
        //     }
        // }

