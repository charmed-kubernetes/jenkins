@Library('juju-pipeline@master') _
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
        stage('Create snap recipes'){
            steps {
                dir('jobs'){
                    sh '''
                       git ls-remote -t --refs https://github.com/kubernetes/kubernetes|sort -t "/" -k 3 -V| \
                        sed -E "s/^[[:xdigit:]]+[[:space:]]+refs\/tags\/(.+)/\1/g" \
                        > includes/k8s-upstream-versions.inc
                    '''.replaceAll('\\s+', ' ')
                }
            }
        }
    }
}
