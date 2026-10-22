def kube_status = "stable"
def kube_version = params.k8s_tag
def kube_ersion = null
if (kube_version != "") {
    kube_ersion = kube_version.substring(1)
}
def snapcraft_channel = "--channel=8.x/stable"
def lxc_name = env.JOB_NAME.replaceAll('\\.', '-')+"-"+env.BUILD_NUMBER

pipeline {
    agent {
        label "${params.build_node}"
    }
    /* XXX: Global $PATH setting doesn't translate properly in pipelines
     https://stackoverflow.com/questions/43987005/jenkins-does-not-recognize-command-sh
     */
    environment {
        HOME            = "/var/lib/jenkins"
        PATH            = "/var/lib/jenkins/venvs/ci/bin:/snap/bin:/usr/sbin:/usr/bin:/sbin:/bin:/usr/local/bin"
        HTTP_PROXY      = "http://egress.ps7.internal:3128"
        HTTPS_PROXY     = "http://egress.ps7.internal:3128"
        http_proxy      = "http://egress.ps7.internal:3128"
        https_proxy     = "http://egress.ps7.internal:3128"
        NO_PROXY        = "localhost,127.0.0.1"
        no_proxy        = "localhost,127.0.0.1"
        ADDONS_ARCHES   = "amd64 arm64 ppc64le s390x"
        GITHUB_CREDS    = credentials('cdkbot_github')
    }
    stages {
        stage('Setup User') {
            steps {
                sh "git config --global user.email 'cdkbot@juju.solutions'"
                sh "git config --global user.name 'cdkbot'"
            }
        }
        stage('Ensure valid K8s version'){
            when {
                expression { kube_version == "" }
            }
            steps {
                script {
                    kube_version = sh(returnStdout: true, script: "curl -L https://dl.k8s.io/release/stable-${params.version}.txt").trim()
                    if(kube_version.indexOf('Error') > 0) {
                        kube_status = "latest"
                        kube_version = sh(returnStdout: true, script: "curl -L https://dl.k8s.io/release/latest-${params.version}.txt").trim()
                    }
                    if(kube_version.indexOf('Error') > 0) {
                        error("Could not determine K8s version for ${params.version}")
                    }
                    kube_ersion = kube_version.substring(1);
                }
            }
        }
        stage('Setup Source') {
            steps {
                sh """
                    ADDONS_BRANCH=release-${params.version}
                    if git ls-remote --exit-code --heads https://github.com/charmed-kubernetes/cdk-addons.git \$ADDONS_BRANCH
                    then
                        echo "Getting cdk-addons from \$ADDONS_BRANCH branch."
                        git clone https://github.com/charmed-kubernetes/cdk-addons.git --branch \$ADDONS_BRANCH --depth 1
                    else
                        echo "Getting cdk-addons from default branch."
                        git clone https://github.com/charmed-kubernetes/cdk-addons.git --depth 1
                        if [ "${kube_status}" = "stable" ]
                        then
                            echo "Creating \$ADDONS_BRANCH for cdk-addons."
                            cd cdk-addons
                            git checkout -b \$ADDONS_BRANCH
                            if ${params.dry_run}
                            then
                                echo "Dry run; would have pushed: \$ADDONS_BRANCH"
                            else
                                git push "https://\${GITHUB_CREDS_USR}:\${GITHUB_CREDS_PSW}@github.com/charmed-kubernetes/cdk-addons.git" --all
                            fi
                            cd -
                        fi
                    fi
                """
            }
        }
        stage('Setup Build Container'){
            steps {
                /* override sh for this step:

                 Needed because cilib.sh has some non POSIX bits.
                */
                script {
                    def core = sh(
                        returnStdout: true, 
                        script: "grep -e '^base:' cdk-addons/cdk-addons.yaml | awk '{ print \$2 }'"
                    ).trim()
                    if(core == "core18" || core == "core16") {
                        snapcraft_channel="--channel=7.x/stable"
                    }
                }

                sh """#!/usr/bin/env bash
                    . \${WORKSPACE}/cilib.sh

                    ci_lxc_launch ubuntu:24.04 ${lxc_name}
                    until sudo lxc shell ${lxc_name} -- bash -c "snap install snapcraft ${snapcraft_channel} --classic"; do
                        echo 'retrying snapcraft install in 3s...'
                        sleep 3
                    done
                    sudo lxc shell ${lxc_name} -- bash -c "apt-get install containerd -y"

                    # we'll upload snaps from within the container; put creds in place
                    sudo lxc file push /var/lib/jenkins/snapcraft-creds ${lxc_name}/snapcraft-creds
                """
            }
        }
        stage('Build Snaps'){
            steps {
                echo "Setting K8s version: ${kube_version} and K8s ersion: ${kube_ersion}"
                sh """
                    cd cdk-addons
                    make KUBE_VERSION=${kube_version} prep

                    for arch in ${env.ADDONS_ARCHES}
                    do
                        echo "Prepping cdk-addons (\${arch}) snap source."
                        curl -fsSL -o build/kubectl https://dl.k8s.io/${kube_version}/bin/linux/\${arch}/kubectl
                        chmod +x build/kubectl
                        sed 's/KUBE_VERSION/${kube_ersion}/g' cdk-addons.yaml > build/snapcraft.yaml
                        if [ "\${arch}" = "ppc64le" ]
                        then
                          arch="ppc64el"
                        fi
                        sed -i "s/KUBE_ARCH/\${arch}/g" build/snapcraft.yaml

                        echo "Copying cdk-addons (\${arch}) into container."
                        sudo lxc shell ${lxc_name} -- bash -c "rm -rf /cdk-addons"
                        sudo lxc file push -q build ${lxc_name}/cdk-addons/ -p -r

                        echo "Build cdk-addons (\${arch}) snap."
                        sudo lxc shell ${lxc_name} -- bash -c \
                            "cd /cdk-addons/build; \
                            snapcraft --destructive-mode --enable-experimental-target-arch --target-arch=\${arch}"
                        sudo lxc shell ${lxc_name} -- bash -c "mv /cdk-addons/build/*.snap /"
                    done
                    cd -
                """
            }
        }
        stage('Upload Snaps'){
            steps {
                script {
                    if(params.dry_run) {
                        echo "Dry run; would have uploaded cdk-addons/*.snap to ${params.channels}"
                    } else {
                        sh """
                            for arch in ${env.ADDONS_ARCHES}
                            do
                                if [ "\${arch}" = "ppc64le" ]
                                then
                                    arch="ppc64el"
                                fi
                                BUILT_SNAP="cdk-addons_${kube_ersion}_\${arch}.snap"

                                echo "Uploading \${BUILT_SNAP}."
                                sudo lxc shell ${lxc_name} -- bash -c \
                                    'export SNAPCRAFT_STORE_CREDENTIALS=\$(< "/snapcraft-creds"); '"snapcraft -v upload /\${BUILT_SNAP} --release ${params.channels}"
                            done
                        """
                    }
                }
            }
        }
    }
    post {
        always {
            sh "echo Disk usage before cleanup"
            sh "df -h -x squashfs -x overlay | grep -vE ' /snap|^tmpfs|^shm'"

            /* override sh since cilib.sh has some non POSIX bits. */
            sh """#!/usr/bin/env bash
                . \${WORKSPACE}/cilib.sh

                ci_lxc_delete ${lxc_name}
                sudo rm -rf cdk-addons/build
            """

            sh "echo Disk usage after cleanup"
            sh "df -h -x squashfs -x overlay | grep -vE ' /snap|^tmpfs|^shm'"
        }
    }
}
