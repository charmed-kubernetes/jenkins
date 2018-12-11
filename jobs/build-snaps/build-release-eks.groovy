@Library('juju-pipeline@master') _

def snap_sh = "tox -e py36 -- python3 build-snaps/snaps.py"
def eks_snaps = '--snap kubelet --snap kubectl --snap kube-proxy --snap kubernetes-test'

pipeline {
    agent {
        label "runner-amd64"
    }
    /* XXX: Global $PATH setting doesn't translate properly in pipelines
     https://stackoverflow.com/questions/43987005/jenkins-does-not-recognize-command-sh
     */
    environment {
        PATH = '/snap/bin:/usr/sbin:/usr/bin:/sbin:/bin:/usr/local/bin'
        GITHUB_CREDS = credentials('cdkbot_github')
    }
    options {
        ansiColor('xterm')
        timestamps()
    }
    stages {
        stage('Setup') {
            steps {
                sh "snapcraft login --with /var/lib/jenkins/snapcraft-cpc-creds"
            }
        }
        stage('Release Snaps'){
            steps {
                dir('jobs'){
                    script {
                        sh "${snap_sh} build --arch amd64 ${eks_snaps} --version ${version}"
                    }
                    sh "${snap_sh} process --match-re \'(?=\\S*[-]*)([a-zA-Z-]+)(.*)\' --rename-re \'\\1-eks_\\2\'"
                    params.channels.split().each { channel ->
                        sh "${snap_sh} release --channel ${version}/${channel}"
                    }
                }
            }
        }
    }
    post {
        always {
            sh "sudo rm -rf jobs/release/snap || true"
            sh "snapcraft logout"
            sh "docker rmi -f \$(docker images | grep \"none\" | awk '/ / { print \$3 }') || true"
            sh "docker rm -f \$(docker ps -qa --no-trunc --filter \"status=exited\") || true"
        }
    }
}
