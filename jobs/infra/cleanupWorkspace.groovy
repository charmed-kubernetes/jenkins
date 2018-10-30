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
        stage('Cleanup workspaces') {
            steps {
                // sh "sudo rm -rf ${params.workspace_path}"
                sh "cd jobs && tox -e py36 -- aws s3 --profile s3 ls s3://jujubigdata"
            }
        }
    }
}
