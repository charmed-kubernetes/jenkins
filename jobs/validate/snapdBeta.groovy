@Library('juju-pipeline@master') _

def juju_model = String.format("%s-%s", params.model, uuid())

pipeline {
    agent {
        label 'runner-amd64'
    }
    /* XXX: Global $PATH setting doesn't translate properly in pipelines
     https://stackoverflow.com/questions/43987005/jenkins-does-not-recognize-command-sh
     */
    environment {
        PATH = "${utils.cipaths}"
    }
    options {
        ansiColor('xterm')
        timestamps()
    }
    stages {
        stage('Run k8s-core job') {
            options {
                timeout(time: 2, unit: 'HOURS')
            }
            steps {
                build job:"validate-v1.14.x-kubernetes-core",
                    parameters: [booleanParam(name:'with_beta_snapd', value: true)]
            }
        }
    }
}
