@Library('juju-pipeline@master') _

def exec(cmd) {
    sh "sudo lxc exec ${CONTAINER} -- bash -c '${cmd}'"
}

boolean ゴゴゴ = false

pipeline {
    agent {
        label 'runner-amd64'
    }
    /* XXX: Global $PATH setting doesn't translate properly in pipelines
     https://stackoverflow.com/questions/43987005/jenkins-does-not-recognize-command-sh
     */
    environment {
        PATH = "${utils.cipaths}"
        CONTAINER = "kubeflow-release-${uuid()}"
    }
    options {
        ansiColor('xterm')
        timestamps()
    }
    stages {
        stage('Set Start Time') {
            steps {
                setStartTime()
            }
        }
        stage('Check for new commits') {
            steps {
                sh 'git clone https://github.com/juju-solutions/bundle-kubeflow.git'
                script {
                    ゴゴゴ = sh(script: 'python3 jobs/build-charms/ddbkf.py check', returnStdout: true).trim() == 'GO'
                }

            }
        }
        stage('Setup LXC') {
            steps {
                sh 'sudo lxc profile show kfpush || sudo lxc profile copy default kfpush'
                sh 'sudo lxc profile edit kfpush < jobs/build-charms/lxc.profile'
                sh "sudo lxc launch -p default -p kfpush ubuntu:18.04 ${CONTAINER}"
                sh "sudo lxc file push -p ~/.go-cookies ${CONTAINER}/root/.go-cookies"
                sh "sudo lxc file push -p ~/.local/share/juju/store-usso-token ${CONTAINER}/root/.local/share/juju/store-usso-token"
            }
            when { expression { ゴゴゴ } }
        }
        stage('Wait for snap') {
            options {
                retry(10)
            }
            steps {
                exec 'sudo snap install core'
            }
            when { expression { ゴゴゴ } }
        }
        stage('Install dependencies') {
            steps {
                exec 'sudo snap install charm --classic'
                exec 'sudo snap install juju --classic'
                exec 'sudo snap install juju-helpers --classic --edge'
                exec 'sudo apt update && sudo apt install -y docker.io'
            }
            when { expression { ゴゴゴ } }
        }
        stage('Release Kubeflow Bundle') {
            steps {
                exec 'git clone https://github.com/juju-solutions/bundle-kubeflow.git'
                exec 'cd bundle-kubeflow && CHARM_BUILD_DIR=/tmp/charms juju bundle publish --url cs:~kubeflow-charmers/kubeflow'
            }
            when { expression { ゴゴゴ } }
        }
        stage('Update DDB') {
            steps {
                sh 'python3 jobs/build-charms/ddbkf.py update'
            }
            when { expression { ゴゴゴ } }
        }
    }
    post {
        success {
            setPass()
        }
        failure {
            setFail()
        }
        always {
            setEndTime()
        }
        cleanup {
            saveMeta()
            sh "sudo lxc delete --force ${CONTAINER} || true"
        }
    }
}
