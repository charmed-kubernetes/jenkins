@Library('juju-pipeline@master') _

pipeline {
    agent { label params.build_node }
    // Add environment credentials for pyjenkins script on configuring nodes automagically
    environment {
        PATH = "${utils.cipaths}"
    }

    options {
        ansiColor('xterm')
        timestamps()
    }
    stages {
        stage("Configure systems") {
            options {
                timeout(time: 30, unit: 'MINUTES')
            }

            steps {
                installToolsJenkaas()
                tearDownLxd()
            }
        }
    }
}
