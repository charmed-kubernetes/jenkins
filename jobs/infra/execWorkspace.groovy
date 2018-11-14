@Library('juju-pipeline@master') _

pipeline {
    agent {
        label "${params.build_node}"
    }
    // Add environment credentials for pyjenkins script on configuring nodes automagically
    environment {
        PATH = "/snap/bin:/usr/sbin:/usr/bin:/sbin:/bin:/usr/local/bin"
    }

    options {
        ansiColor('xterm')
        timestamps()
    }
    stages {
        stage('Running') {
            steps {
                // sh "cd jobs && tox -e py36 -- aws s3 --profile s3 ls s3://jujubigdata"
                sh "sudo ip link list"
                sh "ping -c 1 security.ubuntu.com"
                sh "sudo lxc delete --force piptest || true"
                retry(10){
                    sh "sudo lxc launch ubuntu:16.04 piptest"
                    sh "sudo lxc exec piptest -- /bin/bash -c 'ping -c 1 security.ubuntu.com'"
                    sh "sudo lxc exec piptest -- /bin/bash -c 'apt-get update'"
                    sh "sudo lxc exec piptest -- /bin/bash -c 'apt-get install -qyf python3-pip'"
                    sh "sudo lxc exec piptest -- /bin/bash -c 'pip3 install requests'"
                    sh "sudo lxc exec piptest -- /bin/bash -c 'pip3 install sh'"
                    sh "sudo lxc exec piptest -- /bin/bash -c 'pip3 install launchpadlib'"
                    sh "sudo lxc delete --force piptest"
                }
                // script {
                //     if (params.workspace_path) {
                //         sh "sudo rm -rf ${params.workspace_path}"
                //     }
                //     if (params.exec_command) {
                //         sh "${params.exec_command}"
                //     }
                // }
            }
        }
    }
}
