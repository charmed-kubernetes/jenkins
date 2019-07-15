@Library('juju-pipeline@master') _

def snap_sh = "${utils.cibin}/ogc"

pipeline {
    agent { label "runner-cloud" }
    environment {
        PATH = "${utils.cipaths}"
        // LP API Creds
        LPCREDS = credentials('launchpad_creds')
        // This is the user/pass able to publish snaps to the store via launchpad
        K8STEAMCI = credentials('k8s_team_ci_lp')
        GIT_SSH_COMMAND='ssh -i /var/lib/jenkins/.ssh/cdkbot_rsa -oStrictHostKeyChecking=no'
    }
    options {
        ansiColor('xterm')
        timestamps()
    }
    stages {
        stage('Sync Upstream Releases'){
            steps {
                dir('jobs'){
                    sh "${snap_sh} snap sync-upstream --snap-list includes/k8s-snap-list.inc"
                }
            }
        }
    }
}
