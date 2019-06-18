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
        stage('Validate Calico') {
            steps {
                script {
                    def jobs = [:]
                    def releases = readYaml file: 'jobs/includes/k8s-support-matrix.inc'
                    releases.each { k ->
                        def release = k.keySet().first()
                        def options = k.values()
                        jobs[release] = {
                            stage("Validate Calico: ${options.normalized_ver}") {
                                build job:"validate-calico-${release}",
                                    parameters: [string(name:'cloud', value: 'aws/us-east-1')]
                            }
                        }
                    }
                    parallel jobs
                }
            }
        }
        stage('Validate Vault') {
            steps {
                script {
                    def jobs = [:]
                    def releases = readYaml file: 'jobs/includes/k8s-support-matrix.inc'
                    releases.each { k ->
                        def release = k.keySet().first()
                        def options = k.values()
                        jobs[release] = {
                            stage("Validate Vault: ${options.normalized_ver}") {
                                build job:"validate-vault-${release}",
                                    parameters: [string(name:'cloud', value: 'aws/us-east-1')]
                            }
                        }
                    }
                    parallel jobs
                }
            }
        }
        stage('Validate Tigera EE') {
            steps {
                script {
                    def jobs = [:]
                    def releases = readYaml file: 'jobs/includes/k8s-support-matrix.inc'
                    releases.each { k ->
                        def release = k.keySet().first()
                        def options = k.values()
                        jobs[release] = {
                            stage("Validate Tigera EE: ${options.normalized_ver}") {
                                build job:"validate-tigera-secure-ee-${release}",
                                    parameters: [string(name:'cloud', value: 'aws/us-east-1')]
                            }
                        }
                    }
                    parallel jobs
                }
            }
        }
        stage('Validate NVidia') {
            steps {
                script {
                    def jobs = [:]
                    def releases = readYaml file: 'jobs/includes/k8s-support-matrix.inc'
                    releases.each { k ->
                        def release = k.keySet().first()
                        def options = k.values()
                        stage("Validate NVidia: ${options.normalized_ver}") {
                            build job:"validate-nvidia-${release}",
                                parameters: [string(name:'cloud', value: 'aws/us-east-1')]
                        }
                    }
                }
            }
        }
    }
}
