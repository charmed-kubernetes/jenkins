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
                sh "sudo rm -rf /tmp/sosreport*"
                sh "sudo sosreport --batch"
            }
        }
    }
    post {
        success {
            archiveArtifacts artifacts: '/tmp/sosreport*.tar.xz', fingerprint: true
        }
    }
}
