@Library('juju-pipeline@master') _


pipeline {
    environment {
        PATH = "${utils.cipaths}"
    }
    options {
        ansiColor('xterm')
        timestamps()
    }
    stages {
        stage('Charms') {
            script {
                def jobs = [:]
                def charms = readYaml file: 'jobs/includes/charm-support-matrix.inc'
                charms.each { charm, meta ->
                    jobs[charm] = {
                        stage("Validate: ${charm}") {
                            agent {
                                label 'runner-amd64'
                            }
                            build job:"build-release-${charm}"
                        }
                    }
                }
                parallel jobs
            }
        }
    }
}
