// Uses Juju from master node to create local lxd instances
// To enlist node into jenkins, go into manage nodes and set launch method to execute command on master:
// sudo -E sudo -u jenkins -E juju ssh -m jenkins-agents:default runnerID/0 -- "java -jar /usr/local/bin/slave.jar"

def run_as_j = "sudo -E sudo -u jenkins -E"

pipeline {
    agent {
        label 'master'
    }
    // Add environment credentials for pyjenkins script on configuring nodes automagically
    environment {
        PATH = "/snap/bin:/usr/sbin:/usr/bin:/sbin:/bin:/usr/local/bin"
        JUJU_CONTROLLER = "jenkins-ci"
        JUJU_MODEL = "jenkins-ci:agents"
        RUNNER_ID = "runner${env.BUILD_NUMBER}"
        APIKEY = credentials('apikey')
        APIUSER = credentials('apiuser')
    }

    options {
        ansiColor('xterm')
        timestamps()
    }
    stages {
        stage('Destroy nodes') {
            steps {
                sh "cd jobs && pipenv install"
                sh "cd jobs && pipenv run invoke delete-nodes --apikey ${env.APIKEY} --apiuser ${env.APIUSER}"
                sh "${run_as_j} juju destroy-model -y ${env.JUJU_MODEL}"
                sh "${run_as_j} juju add-model -c ${env.JUJU_CONTROLLER} agents"
            }
        }
        stage('Create nodes') {
            steps {
                sh "${run_as_j} juju deploy -m ${env.JUJU_MODEL} --series bionic cs:ubuntu ${env.RUNNER_ID}"
                sh "${run_as_j} juju-wait -e ${env.JUJU_MODEL} -w"
                sh "${run_as_j} juju ssh -m ${env.JUJU_MODEL} ${env.RUNNER_ID}/0 -- wget https://ci.kubernetes.juju.solutions/jnlpJars/slave.jar"
                sh "${run_as_j} juju ssh -m ${env.JUJU_MODEL} ${env.RUNNER_ID}/0 -- sudo apt install -qyf default-jre"
                sh "cd jobs && pipenv run invoke create-nodes --apikey ${env.APIKEY} --apiuser ${env.APIUSER} --node ${env.RUNNER_ID}"
            }
        }
    }
}
