@Library('juju-pipeline@master') _

def nodes = ['runner-amd64', 'runner-amd64-2', 'runner-s390x', 'runner-arm64', 'runner-ppc64le']

pipeline {
    agent none
    // Add environment credentials for pyjenkins script on configuring nodes automagically
    environment {
        PATH = "/snap/bin:/usr/sbin:/usr/bin:/sbin:/bin:/usr/local/bin"
    }

    options {
        ansiColor('xterm')
        timestamps()
    }
    stages {
        script {
            nodes.each { node ->
                agent {
                    label node
                }
                stage("Configure systems: ${node}") {
                    steps {
                        installToolsJenkaas()
                        // dir("jobs/infra") {
                        //     sh "/usr/local/bin/pipenv run ansible-playbook playbook-jenkins.yml -e 'ansible_python_interpreter=python3'"
                        // }
                    }
                }
            }
        }
    }
}
