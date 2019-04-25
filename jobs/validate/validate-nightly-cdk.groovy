@Library('juju-pipeline@master') _

// Performs parallel job builds for validating cdk

pipeline {
    agent { label 'runner-cloud' }
    environment {
        PATH = "${utils.cipaths}"
    }
    options {
        ansiColor('xterm')
        timestamps()
    }
    stages {
        stage('Validate') {
            steps {
                script {
                    def jobs = [:]
                    def releases = readYaml file: 'jobs/includes/k8s-support-matrix.inc'
                    releases.each { k ->
                        def release = k.keySet().first()
                        def options = k.values()
                        jobs[release] = {
                            stage("Validate: ${options.normalized_ver}") {
                                build job:"validate-${release}-canonical-kubernetes",
                                    parameters: [string(name:'cloud', value: 'aws/us-east-1')]
                            }
                        }
                    }
                    parallel jobs
                }
            }
        }
    }
}
