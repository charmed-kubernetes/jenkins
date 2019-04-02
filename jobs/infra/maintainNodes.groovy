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
            steps {
                installToolsJenkaas()
                tearDownLxd()
            }
        }
    }
}
