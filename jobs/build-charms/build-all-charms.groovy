@Library('juju-pipeline@master') _


pipeline {
    agent { label 'runner-amd64' }
    environment {
        PATH = "${utils.cipaths}"
    }
    options {
        ansiColor('xterm')
        timestamps()
    }
    stages {
        stage('K8s Charms') {
            steps {
                script {
                    def jobs = [:]
                    // returns a LinkedHashMap
                    def charms = readYaml file: 'jobs/includes/charm-support-matrix.inc'
                    charms.each { k ->
                        // Each item is a LinkedHashSet, so we pull the first item from the set
                        // since there is only 1 key per charm
                        def charm = k.keySet().first()
                        if (k[charm].namespace != 'containers') {
                            return
                        }

                        jobs[charm] = {
                            stage("Validate: ${charm}") {
                                build job:"build-release-${charm}"
                            }
                        }
                    }
                    parallel jobs
                }
            }
        }
        stage('K8s Extras Charms') {
            steps {
                script {
                    def jobs = [:]
                    // returns a LinkedHashMap
                    def charms = readYaml file: 'jobs/includes/charm-support-matrix.inc'
                    charms.each { k ->
                        // Each item is a LinkedHashSet, so we pull the first item from the set
                        // since there is only 1 key per charm
                        def charm = k.keySet().first()
                        if(k[charm].namespace != 'kubeflow-charmers') {
                            return
                        }
                        jobs[charm] = {
                            stage("Validate: ${charm}") {
                                build job:"build-release-${charm}"
                            }
                        }
                    }
                    parallel jobs
                }
            }
        }

        stage('Bundles') {
            steps {
                build job:"build-release-bundles"
            }
        }
        stage('Report') {
            steps {
                build job:"generate-reports-overview"
            }
        }
    }
}
