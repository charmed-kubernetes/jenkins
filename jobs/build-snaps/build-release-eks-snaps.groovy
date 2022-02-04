@Library('juju-pipeline@master') _

def kube_version = params.k8s_tag
def kube_ersion = kube_version.substring(1)
def lxc_name = env.JOB_NAME+"-"+env.BUILD_NUMBER

pipeline {
    agent {
        label "${params.build_node}"
    }
    /* XXX: Global $PATH setting doesn't translate properly in pipelines
     https://stackoverflow.com/questions/43987005/jenkins-does-not-recognize-command-sh
     */
    environment {
        PATH = "${utils.cipaths}"
        CK_SNAPS = "kubectl kubelet kubernetes-test kube-proxy"
        EKS_BASE = "core20"
        EKS_SUFFIX = "-eks"
    }
    options {
        ansiColor('xterm')
        timestamps()
    }
    stages {
        stage('Setup User') {
            steps {
                sh """
                    snapcraft logout
                    snapcraft login --with /var/lib/jenkins/.config/snapcraft/snapcraft-cpc.cfg
                    snapcraft whoami
                """
            }
        }
        stage('Setup Source') {
            steps {
                sh """
                    CK_SNAP_BRANCH="${kube_version}"
                    CK_SNAP_REPO_PREFIX="https://git.launchpad.net/snap-"

                    for snap in ${env.CK_SNAPS}
                    do
                        CK_SNAP_REPO="\${CK_SNAP_REPO_PREFIX}\${snap}"
                        EKS_SNAP="\${snap}${env.EKS_SUFFIX}"

                        if git ls-remote --exit-code --heads \${CK_SNAP_REPO} \${CK_SNAP_BRANCH}
                        then
                            echo "Getting \${snap} from \${CK_SNAP_BRANCH} branch."
                            git clone \${CK_SNAP_REPO} --branch \${CK_SNAP_BRANCH} --depth 1 \${EKS_SNAP}
                        else
                            echo "ERROR: \${CK_SNAP_BRANCH} branch not found in the \${CK_SNAP_REPO} repo."
                            exit 1
                        fi

                        # eks snaps have a suffix and different base than ck; adjust snapcraft.yaml
                        cd \${EKS_SNAP}
                        sed -i -e "s/^name: \${snap}/name: \${EKS_SNAP}/" \
                               -e "s/^base: .*/base: ${env.EKS_BASE}/" snapcraft.yaml
                        cd -
                    done
                """
            }
        }
        stage('Setup Build Container'){
            steps {
                sh """
                    source \$(dirname \${BASH_SOURCE:-\$0})/../../cilib.sh

                    ci_lxc_launch ubuntu:20.04 ${lxc_name}
                    until sudo lxc shell ${lxc_name} -- bash -c 'snap install snapcraft --classic'; do
                        echo 'retrying snapcraft install in 3s...'
                        sleep 3
                    done
                """
            }
        }
        stage('Build EKS Snaps'){
            steps {
                sh """
                    for snap in ${env.CK_SNAPS}
                    do
                        EKS_SNAP="\${snap}${env.EKS_SUFFIX}"

                        echo "Building \${EKS_SNAP}."
                        cd \${EKS_SNAP}
                        SNAPCRAFT_BUILD_ENVIRONMENT=host snapcraft
                        mv *.snap ..
                        cd -
                    done
                """
            }
        }
        stage('Push EKS Snaps'){
            steps {
                script {
                    if(params.dry_run) {
                        echo "Dry run; would have uploaded *.snap to ${params.channels}"
                    }
                }
            }
        }
    }
    post {
        always {
            sh "sudo lxc delete -f ${lxc_name}"
            sh "snapcraft logout"
        }
    }
}
