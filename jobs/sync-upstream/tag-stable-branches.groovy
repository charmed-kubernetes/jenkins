@Library('juju-pipeline@master') _

pipeline {
    agent {
        label 'runner'
    }
    environment {
        PATH = "${utils.cipaths}"
        CDKBOT_GH = credentials('cdkbot_github')
    }
    options {
        ansiColor('xterm')
        timestamps()
    }
    stages {
        stage('Tag stable branches'){
            steps {
                dir("jobs") {
                    sh "CDKBOT_GH=${CDKBOT_GH} ${utils.cipy} sync-upstream/sync.py tag-stable --layer-list includes/charm-layer-list.inc --bundle-revision ${params.bundle_rev}"
                }
            }
        }
    }
}
