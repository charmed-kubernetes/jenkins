@Library('juju-pipeline@master') _

pipeline {
    agent {
        label 'runner'
    }
    // Add environment credentials for pyjenkins script on configuring nodes automagically
    environment {
        PATH = "/snap/bin:/usr/sbin:/usr/bin:/sbin:/bin:/usr/local/bin"
    }

    options {
        ansiColor('xterm')
        timestamps()
    }
    stages {
        stage('Configure systems') {
            steps {
                installTools()
                dir("jobs/infra") {
                    sh "/usr/local/bin/pipenv run ansible-playbook playbook-jenkins.yml -e 'ansible_python_interpreter=python3'"
                }
            }
        }
    }
}
