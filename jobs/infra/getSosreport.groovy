@Library('juju-pipeline@master') _

pipeline {
    agent {
        label "${params.build_node}"
    }
    // Add environment credentials for pyjenkins script on configuring nodes automagically
    environment {
        PATH = "${utils.cipaths}"
    }

    options {
        ansiColor('xterm')
        timestamps()
    }
    stages {
        stage('Get sosreport') {
            steps {
                sh "sudo rm -rf sosreport"
                sh "mkdir -p sosreport"
                sh "sudo sosreport --batch --tmp-dir sosreport --name jenkins-${params.build_nade}"
                sh "sudo chown -R jenkins:jenkins sosreport"

            }
        }
    }
    post {
        success {
            archiveArtifacts artifacts: "sosreport/*", fingerprint: true
        }
    }
}
