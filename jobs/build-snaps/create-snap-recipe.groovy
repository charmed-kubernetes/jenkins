@Library('juju-pipeline@master') _

/* Creates a snap recipe within launchpad so that the branch can be
 automatically built and pushed to snap store
 */

def snap_sh = "tox -e py36 -- python3 build-snaps/snaps-source.py"

/* LPCREDS=~/Documents/lp-creds.yml tox --workdir .tox -e py36 -- python3 build-snaps/snaps-source.py builder \
 --snap kube-apiserver --version 1.13 --track '1.13/edge/test-k8s-source' \
 --owner k8s-jenkaas-admins --branch 1.13.2 \
 --repo git+ssh://cdkbot@git.launchpad.net/snap-kube-apiserver
 */


pipeline {
    agent {
        label "runner"
    }
    /* XXX: Global $PATH setting doesn't translate properly in pipelines
     https://stackoverflow.com/questions/43987005/jenkins-does-not-recognize-command-sh
     */
    environment {
        PATH = '/snap/bin:/usr/sbin:/usr/bin:/sbin:/bin:/usr/local/bin'
        // LP API Creds
        LPCREDS = credentials('launchpad_creds')
        // This is the user/pass able to publish snaps to the store via launchpad
        K8STEAMCI = credentials('k8s_team_ci_lp')
    }
    options {
        ansiColor('xterm')
        timestamps()
    }
    stages {
        stage('Create snap recipes'){
            steps {
                dir('jobs'){
                    sh "LPCREDS=${env.LPCREDS} ${snap_sh} builder --snap ${params.snap} --version ${params.version} --track '${params.track} --owner ${params.owner} --branch ${params.branch} --repo git+ssh://cdkbot@git.launchpad.net/snap-${params.snap} --snap-recipe-email '${env.K8STEAMCI_USR}' --snap-recipe-password '${env.K8STEAMCI_PWD}'"
                }
            }
        }
    }
}
