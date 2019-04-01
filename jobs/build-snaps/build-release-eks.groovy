@Library('juju-pipeline@master') _

def snap_sh = "${utils.cipy} build-snaps/snaps.py"
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
                        if(!params.release_only){
                            sh "${snap_sh} build --arch amd64 ${eks_snaps} --version ${version} --match-re \'(?=\\S*[-]*)([a-zA-Z-]+)(.*)\' --rename-re \'\\1-eks'"
                            sh "sudo chown jenkins:jenkins -R release/snap"
                            sh "${snap_sh} push || true"
                        }
                        def snaps_to_release = ['kubelet-eks', 'kubectl-eks', 'kube-proxy-eks', 'kubernetes-test-eks']
                        params.channels.split().each { channel ->
                            snaps_to_release.each  { snap ->
                                if(params.dry_run) {
                                    sh "${snap_sh} release --name ${snap} --channel ${channel} --version ${version} --dry-run"
                                } else {
                                    sh "${snap_sh} release --name ${snap} --channel ${channel} --version ${version}"
                                }

                            }
                        }
                    }
                }
            }
        }
    }
    post {
        always {
            sh "sudo rm -rf jobs/release/snap || true"
            sh "snapcraft logout"
            sh "docker image prune -a --filter \"until=24h\" --force"
            sh "docker container prune --filter \"until=24h\" --force"
        }
    }
}
