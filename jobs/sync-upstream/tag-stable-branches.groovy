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
                    script {
                        if(params.dry_run) {
                            sh "CDKBOT_GH=${CDKBOT_GH} ${utils.cipy} sync-upstream/sync.py tag-stable --layer-list includes/charm-layer-list.inc --charm-list includes/charm-support-matrix.inc --bundle-revision ${params.bundle_rev} --dry-run"
                        } else {
                            sh "CDKBOT_GH=${CDKBOT_GH} ${utils.cipy} sync-upstream/sync.py tag-stable --layer-list includes/charm-layer-list.inc --charm-list includes/charm-support-matrix.inc --bundle-revision ${params.bundle_rev}"
                        }
                    }
                }
            }
        }
    }
}
