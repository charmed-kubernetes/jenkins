@Library('juju-pipeline@master') _

pipeline {
    agent {
        label "${param.build_node}"
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
                sh "sudo rm -rf ${param.workspace_path}"
            }
        }
    }
}
