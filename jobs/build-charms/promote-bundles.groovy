@Library('juju-pipeline@master') _

def to_channels = params.to_channel.split()
def charm_sh = "${utils.cipy} build-charms/charms.py"

pipeline {
    agent { label 'runner-amd64' }
    /* XXX: Global $PATH setting doesn't translate properly in pipelines
     https://stackoverflow.com/questions/43987005/jenkins-does-not-recognize-command-sh
     */
    environment {
        PATH = "${utils.cipaths}"
    }
    options {
        ansiColor('xterm')
        timestamps()
    }
    stages {
        stage('Promotes bundles to Store') {
            options {
                timeout(time: 45, unit: 'MINUTES')
            }
            steps {
                dir('jobs') {
                    sh "${charm_sh} promote --charm-list includes/charm-bundles-list.inc --filter-by-tag ${params.tag} --from-channel ${params.from_channel} --to-channel ${params.to_channel}"
                }
            }
        }
    }
}
