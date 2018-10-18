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
        stage('Get sosreport') {
            steps {
                sh "sudo rm -rf ${env.WORKSPACE}/sosreport"
                sh "sudo sosreport --batch --tmp-dir ${env.WORKSPACE}/sosreport --name jenkins"
                sh "sudo chown -R jenkins:jenkins ${env.WORKSPACE}/sosreport"

            }
        }
    }
    post {
        success {
            archiveArtifacts artifacts: "${env.WORKSPACE}/sosreport/*", fingerprint: true
        }
    }
}
