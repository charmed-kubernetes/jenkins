@Library('juju-pipeline@master') _

pipeline {
    agent {
        label "charm-runner"
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
        stage('Bootstrap') {
            steps {
                destroy('charm-runner')
                bootstrap('aws', 'charm-runner')
            }
        }
    }
}
