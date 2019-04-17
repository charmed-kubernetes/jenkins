@Library('juju-pipeline@master') _

// Performs parallel job builds for validating cdk

pipeline {
    environment {
        PATH = "${utils.cipaths}"
    }
    options {
        ansiColor('xterm')
        timestamps()
    }
    stages {
        stage('Validate') {
            script {
                def jobs = [:]
                def releases = readYaml file: 'jobs/includes/k8s-support-matrix.inc'
                releases.each { version, release ->
                    jobs[release.normalized_ver] = {
                        stage("Validate: ${release.normalized_ver}") {
                            agent {
                                label 'runner-cloud'
                            }
                            build job:"validate-${version}-canonical-kubernetes",
                                parameters: [string(name:'cloud', value: 'google/us-east1')]
                        }
                    }
                }
                parallel jobs
            }
        }
    }
}
