@Library('juju-pipeline@master') _

/* Creates a snap recipe within launchpad so that the branch can be
 automatically built and pushed to snap store
 */

def snap_sh = "${utils.cipy} build-snaps/snaps-source.py"
def snaps = readYaml text: params.snaps


pipeline {
    agent {
        label "runner"
    }
    /* XXX: Global $PATH setting doesn't translate properly in pipelines
     https://stackoverflow.com/questions/43987005/jenkins-does-not-recognize-command-sh
     */
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
                    script {
                        snaps.each { snap ->
                            sh "${snap_sh} branch --to-branch ${params.tag} --repo git+ssh://cdkbot@git.launchpad.net/snap-${snap} ${utils.debug_out}"
                            sh "LPCREDS=${env.LPCREDS} ${snap_sh} create-snap-recipe --snap ${snap} --version ${params.version} --track '${params.track}' --owner ${params.owner} --tag ${params.tag} --repo git+ssh://cdkbot@git.launchpad.net/snap-${snap} --snap-recipe-email '${env.K8STEAMCI_USR}' --snap-recipe-password '${env.K8STEAMCI_PSW}' ${utils.debug_out}"
                        }
                    }
                }
            }
        }
    }
}
