@Library('juju-pipeline@master') _

def kube_version = params.k8s_tag
def kube_ersion = kube_version.substring(1)
def channels = params.channels.tokenize(',').collect { kube_ersion + '/' + it }.join(',')
def lxc_name = env.JOB_NAME+"-"+env.BUILD_NUMBER
def _find_eks_base(version, override){
    if (override.length())
        return override
    
    // assumes the version looks like r'v\d.\d+.\d+'
    def f_version = Float.parseFloat(version.substring(1, version.lastIndexOf('.')))
    return f_version >= 1.99 ? "core22" : "core20";
}
def eks_base_override = params.eks_base_override
def EKS_BASE = _find_eks_base(kube_version, eks_base_override)
def GO_VERSION = params.eks_go_override

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
                               -e "s/^base: .*/base: ${EKS_BASE}/" \
                               -e "s/install-mode: .*/install-mode: disable/" snapcraft.yaml

                        # update the go version if overriden
                        if [ -n "${GO_VERSION}" ]; then
                            sed -i -e "s#go/.*#${GO_VERSION}#g" snapcraft.yaml
                        fi

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
                            'set -a; add-arg() { \$SNAPCRAFT_PART_BUILD/shared/add-arg-to-configure-hook \$@; }; set +a; '"cd /\${EKS_SNAP};"' snapcraft --destructive-mode'
                    done
                """
            }
        }
        stage('Upload Snaps'){
            steps {
                script {
                    if(params.dry_run) {
                        echo "Dry run; would have uploaded snaps to ${channels}"
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
                                    "snapcraft -v upload /\${EKS_SNAP}/\${BUILT_SNAP} --release ${channels}"
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
