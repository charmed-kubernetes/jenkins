@Library('juju-pipeline@master') _

pipeline {
    agent { label params.build_node }
    // Add environment credentials for pyjenkins script on configuring nodes automagically
    environment {
        PATH = "/snap/bin:/usr/sbin:/usr/bin:/sbin:/bin:/usr/local/bin"
    }

    options {
        ansiColor('xterm')
        timestamps()
    }
    stages {
        stage("Configure systems") {
            steps {
                installToolsJenkaas()
                dir("jobs") {
                    sh "tox -e py36 -- ansible-playbook infra/playbook-jenkins.yml -e 'ansible_python_interpreter=python3'"
                }
            }
        }
    }
}
