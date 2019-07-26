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
        stage('Validate CDK') {
            options {
                timeout(time: 8, unit: 'HOURS')
            }
            steps {
                script {
                    def releases = readYaml file: 'jobs/includes/k8s-support-matrix.inc'
                    releases.each { k ->
                        def release = k.keySet().first()
                        def options = k.values()
                        stage("Validate: ${options.normalized_ver}") {
                            build job:"validate-${release}-canonical-kubernetes", propagate: false,
                                parameters: [string(name:'cloud', value: 'aws/us-east-2')]
                        }
                        stage("Validate: ${options.normalized_ver}") {
                            build job:"validate-calico-${release}", propagate: false,
                                parameters: [string(name:'cloud', value: 'aws/us-east-2')]
                        }
                        stage("Validate: ${options.normalized_ver}") {
                            build job:"validate-ceph-${release}", propagate: false,
                                parameters: [string(name:'cloud', value: 'aws/us-east-2')]
                        }

                        stage("Validate: ${options.normalized_ver}") {
                            build job:"validate-vault-${release}", propagate: false,
                                parameters: [string(name:'cloud', value: 'aws/us-east-2')]
                        }
                        stage("Validate: ${options.normalized_ver}") {
                            build job:"validate-tigera-secure-ee-${release}", propagate: false,
                                parameters: [string(name:'cloud', value: 'aws/us-east-2')]
                        }
                        stage("Validate: ${options.normalized_ver}") {
                            build job:"validate-nvidia-${release}", propagate: false,
                                parameters: [string(name:'cloud', value: 'aws/us-east-2')]
                        }
                    }
                }
            }
        }
    }
}
