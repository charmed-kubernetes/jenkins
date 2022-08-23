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
        stage('Verify User') {
            /* Do this early; we want to fail fast if we don't have valid creds. */
            steps {
                sh """
                    snapcraft login --with /var/lib/jenkins/.config/snapcraft/snapcraft-cpc.cfg
                    snapcraft whoami
                    snapcraft logout
                """
            }
        }
        stage('Setup Source') {
            steps {
                sh """
                    CK_SNAP_BRANCH="${kube_version}"
                    CK_SNAP_REPO_PREFIX="https://git.launchpad.net/snap-"

                    for snap in ${CK_SNAPS}
                    do
                        CK_SNAP_REPO="\${CK_SNAP_REPO_PREFIX}\${snap}"
                        EKS_SNAP="\${snap}${EKS_SUFFIX}"

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
                               -e "s/^base: .*/base: ${EKS_BASE}/" snapcraft.yaml

                        # if we don't have any base defined at this point, add one
                        grep -q "^base: " snapcraft.yaml || echo "base: ${EKS_BASE}" >> snapcraft.yaml

                        echo "Prepared the following snapcraft.yaml:"
                        cat snapcraft.yaml
                        cd -
                    done
                """
            }
        }
        stage('Setup Build Container'){
            steps {
                /* override sh for this step:

                 Needed because cilib.sh has some non POSIX bits.
                 */
                sh """#!/usr/bin/env bash
                    . \${WORKSPACE}/cilib.sh

                    ci_lxc_launch ubuntu:20.04 ${lxc_name}
                    until sudo lxc shell ${lxc_name} -- bash -c "snap install snapcraft --classic"; do
                        echo 'retrying snapcraft install in 3s...'
                        sleep 3
                    done

                    for snap in ${CK_SNAPS}
                    do
                        EKS_SNAP="\${snap}${EKS_SUFFIX}"

                        echo "Copying \${EKS_SNAP} into container."
                        sudo lxc file push \${EKS_SNAP} ${lxc_name}/ -p -r
                    done

                    # we'll upload from within the container; put creds in place
                    sudo lxc file push /var/lib/jenkins/.config/snapcraft/snapcraft-cpc.cfg ${lxc_name}/snapcraft-cpc.cfg
                """
            }
        }
        stage('Build Snaps'){
            steps {
                sh """
                    for snap in ${CK_SNAPS}
                    do
                        EKS_SNAP="\${snap}${EKS_SUFFIX}"

                        echo "Building \${EKS_SNAP}."
                        # NB: kubelet snapcraft.yaml defines an alias, but
                        # aliases wont work in 'bash -c'. Define a func that
                        # is functionally equivalent to the alias. Single quote
                        # it because we need literal vars passed to 'bash -c'.
                        sudo lxc shell ${lxc_name} -- bash -c \
                            'set -a; add-arg() { \$SNAPCRAFT_PART_BUILD/shared/add-arg-to-configure-hook \$@; }; set +a; '"cd /\${EKS_SNAP};"' SNAPCRAFT_BUILD_ENVIRONMENT=host snapcraft'
                    done
                """
            }
        }
        stage('Upload Snaps'){
            steps {
                script {
                    if(params.dry_run) {
                        echo "Dry run; would have uploaded snaps to ${params.channels}"
                    } else {
                        sh """
                            BUILD_ARCH=\$(dpkg --print-architecture)

                            sudo lxc shell ${lxc_name} -- bash -c "snapcraft login --with /snapcraft-cpc.cfg"
                            for snap in ${CK_SNAPS}
                            do
                                EKS_SNAP="\${snap}${EKS_SUFFIX}"
                                BUILT_SNAP="\${EKS_SNAP}_${kube_ersion}_\${BUILD_ARCH}.snap"

                                echo "Uploading \${BUILT_SNAP}."
                                sudo lxc shell ${lxc_name} -- bash -c \
                                    "snapcraft -v upload /\${EKS_SNAP}/\${BUILT_SNAP} --release ${params.channels}"
                            done
                            sudo lxc shell ${lxc_name} -- bash -c "snapcraft logout"
                        """
                    }
                }
            }
        }
    }
    post {
        always {
            /* override sh for this step:

             Needed because cilib.sh has some non POSIX bits.
             */
            sh """#!/usr/bin/env bash
                . \${WORKSPACE}/cilib.sh

                ci_lxc_delete ${lxc_name}
            """
        }
    }
}
