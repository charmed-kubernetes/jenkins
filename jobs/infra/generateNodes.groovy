// Uses Juju from master node to create local lxd instances
// To enlist node into jenkins, go into manage nodes and set launch method to execute command on master:
// sudo -E sudo -u jenkins -E juju ssh -m jenkins-agents:default runnerID/0 -- "java -jar /usr/local/bin/slave.jar"

import java.text.SimpleDateFormat
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
        RUNNER = "runner"
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
                script {
                    // make parallel
                    for (int t = 0; t < 5; t++) {
                        def dateFormat = new SimpleDateFormat("yyyyMMddHHmm")
                        def date = new Date()
                        def runner_id = String.format("%s%s", env.RUNNER, dateFormat.format(date))
                        sh "${run_as_j} juju deploy -m ${env.JUJU_MODEL} --series bionic cs:ubuntu ${runner_id}"
                        sh "${run_as_j} juju-wait -e ${env.JUJU_MODEL} -w"
                        sh "${run_as_j} juju ssh -m ${env.JUJU_MODEL} ${runner_id}/0 -- wget https://ci.kubernetes.juju.solutions/jnlpJars/slave.jar"
                        sh "${run_as_j} juju ssh -m ${env.JUJU_MODEL} ${runner_id}/0 -- sudo apt install -qyf python"
                        sh "cd jobs && pipenv run invoke create-nodes --apikey ${env.APIKEY} --apiuser ${env.APIUSER} --node ${runner_id}"
                    }
                }
            }
        }
        stage('Configure system') {
            steps {
                sh "cd jobs && pipenv run invoke set-node-ips"
                sh "cd jobs/infra && pipenv run ansible-playbook playbook.yml -i hosts --private-key '/var/lib/jenkins/.local/share/juju/ssh/juju_id_rsa'"
            }
        }
    }
}
