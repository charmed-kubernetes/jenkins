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
        stage('Running') {
            steps {
                script {
                    if (params.workspace_path) {
                        sh "sudo rm -rf ${params.workspace_path}"
                    }
                    if (params.exec_command) {
                        sh "${params.exec_command}"
                    }
                    if (params.calculate_space) {
                        sh "du -h --max-depth=1 ${params.calculate_space}"
                    }
                    if (params.script) {
                        writeFile file: 'node_script', text: params.script
                        sh "chmod +x node_script"
                        sh "./node_script"
                    }
                }
            }
        }
    }
}
