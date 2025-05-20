@Library('juju-pipeline@master') _

def bundle_image_file = "./bundle/container-images.txt"
def kube_status = "stable"
def kube_version = params.k8s_tag
def kube_ersion = null
if (kube_version != "") {
    kube_ersion = kube_version.substring(1)
}
def snapcraft_channel = ""
def lxc_name = env.JOB_NAME.replaceAll('\\.', '-')+"-"+env.BUILD_NUMBER

pipeline {
    agent {
        label "${params.build_node}"
    }
    /* XXX: Global $PATH setting doesn't translate properly in pipelines
     https://stackoverflow.com/questions/43987005/jenkins-does-not-recognize-command-sh
     */
    environment {
        PATH = "${utils.cipaths}"
        ADDONS_ARCHES="amd64 arm64 ppc64le s390x"
        GITHUB_CREDS = credentials('cdkbot_github')
        REGISTRY_CREDS = credentials('canonical_registry')
        REGISTRY_URL = 'upload.rocks.canonical.com:5000'
        REGISTRY_REPLACE = 'k8s.gcr.io/ us.gcr.io/ docker.io/library/ docker.io/ gcr.io/ nvcr.io/ quay.io/ registry.k8s.io/'
    }
    options {
        ansiColor('xterm')
        timestamps()
    }
    stages {
        stage('Setup User') {
            /* Do this early; we want to fail fast if we don't have valid creds. */
            steps {
                sh "git config --global user.email 'cdkbot@juju.solutions'"
                sh "git config --global user.name 'cdkbot'"
                sh "snapcraft login --with /var/lib/jenkins/snapcraft-creds"
                sh "snapcraft whoami"
                sh "snapcraft logout"
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
                                git push https://${env.GITHUB_CREDS_USR}:${env.GITHUB_CREDS_PSW}@github.com/charmed-kubernetes/cdk-addons.git --all
                            fi
                            cd -
                        fi
                    fi
                """
                sh "git clone https://github.com/charmed-kubernetes/bundle.git"
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

                    ci_lxc_launch ubuntu:20.04 ${lxc_name}
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
                    make KUBE_VERSION=${kube_version} prep 2>/dev/null

                    for arch in ${env.ADDONS_ARCHES}
                    do
                        echo "Prepping cdk-addons (\${arch}) snap source."
                        wget -O build/kubectl https://dl.k8s.io/${kube_version}/bin/linux/\${arch}/kubectl
                        chmod +x build/kubectl
                        sed 's/KUBE_VERSION/${kube_ersion}/g' cdk-addons.yaml > build/snapcraft.yaml
                        if [ "\${arch}" = "ppc64le" ]
                        then
                          arch="ppc64el"
                        fi
                        sed -i "s/KUBE_ARCH/\${arch}/g" build/snapcraft.yaml

                        echo "Copying cdk-addons (\${arch}) into container."
                        sudo lxc shell ${lxc_name} -- bash -c "rm -rf /cdk-addons"
                        sudo lxc file push . ${lxc_name}/ -p -r

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
        stage('Process Images'){
            steps {
                sh """
                    # Keys from the bundle_image_file used to identify images per release
                    STATIC_KEY=v${params.version}-static:
                    UPSTREAM_KEY=${kube_version}-upstream:

                    # Keep track of images we need to massage as well what we report
                    ALL_IMAGES=""
                    REPORT_IMAGES=""

                    for arch in ${env.ADDONS_ARCHES}
                    do
                        ARCH_IMAGES=\$(grep -e \${STATIC_KEY} -e \${UPSTREAM_KEY} ${bundle_image_file} | sed -e "s|\${STATIC_KEY}||g" -e "s|\${UPSTREAM_KEY}||g" -e "s|{{ arch }}|\${arch}|g" -e "s|{{ multiarch_workaround }}||g")
                        ALL_IMAGES="\${ALL_IMAGES} \${ARCH_IMAGES}"
                    done

                    # Clean up dupes by making a sortable list, uniq it, and turn it back to a string
                    ALL_IMAGES=\$(echo "\${ALL_IMAGES}" | xargs -n1 | sort -u | xargs)

                    # We pull images from staging and push to our production location
                    PROD_PREFIX=${env.REGISTRY_URL}/cdk
                    STAGING_PREFIX=${env.REGISTRY_URL}/staging/cdk

                    for i in \${ALL_IMAGES}
                    do
                        # Set appropriate production/staging image name
                        RAW_IMAGE=\${i}
                        for repl in ${env.REGISTRY_REPLACE}
                        do
                            if echo \${RAW_IMAGE} | grep -qi \${repl}
                            then
                                RAW_IMAGE=\$(echo \${RAW_IMAGE} | sed -e "s|\${repl}||g")
                                break
                            fi
                        done
                        PROD_IMAGE=\${PROD_PREFIX}/\${RAW_IMAGE}
                        STAGING_IMAGE=\${STAGING_PREFIX}/\${RAW_IMAGE}

                        # Report yet skip pull/tag/push images that we already host in rocks.
                        if echo \${RAW_IMAGE} | grep -qi -e 'rocks.canonical.com' -e 'image-registry.canonical.com'
                        then
                            REPORT_IMAGES="\${REPORT_IMAGES} \${RAW_IMAGE}"
                            continue
                        else
                            # Add rocks/cdk prefix (cant use PROD_IMAGE because that would be upload.rocks.c.c)
                            REPORT_IMAGES="\${REPORT_IMAGES} rocks.canonical.com/cdk/\${RAW_IMAGE}"
                        fi

                        if ${params.dry_run}
                        then
                            echo "Dry run; would have pulled: \${STAGING_IMAGE}"
                        else
                            # simple retry if initial pull fails
                            if ! sudo lxc exec ${lxc_name} -- ctr content fetch \${STAGING_IMAGE} --all-platforms --user "${env.REGISTRY_CREDS_USR}:${env.REGISTRY_CREDS_PSW}" >/dev/null
                            then
                                echo "Retrying pull"
                                sleep 5
                                sudo lxc exec ${lxc_name} -- ctr content fetch \${STAGING_IMAGE} --all-platforms --user "${env.REGISTRY_CREDS_USR}:${env.REGISTRY_CREDS_PSW}" >/dev/null
                            fi
                        fi

                        # Tag and push
                        if ${params.dry_run}
                        then
                            echo "Dry run; would have tagged: \${STAGING_IMAGE}"
                            echo "Dry run; would have pushed: \${PROD_IMAGE}"
                        else
                            sudo lxc exec ${lxc_name} -- ctr image tag \${STAGING_IMAGE} \${PROD_IMAGE}
                            # simple retry if initial push fails
                            if ! sudo lxc exec ${lxc_name} -- ctr image push \${PROD_IMAGE} --user "${env.REGISTRY_CREDS_USR}:${env.REGISTRY_CREDS_PSW}" >/dev/null
                            then
                                echo "Retrying push"
                                sleep 5
                                sudo lxc exec ${lxc_name} -- ctr image push \${PROD_IMAGE} --user "${env.REGISTRY_CREDS_USR}:${env.REGISTRY_CREDS_PSW}" >/dev/null
                            fi
                        fi
                    done

                    # Commit what we know about our images
                    cd bundle
                    REPORT_FILE=container-images/${kube_version}.txt
                    echo \${REPORT_IMAGES} | xargs -n1 | sort -u > \${REPORT_FILE}
                    git pull origin main
                    git add \${REPORT_FILE}
                    if git status | grep -qi "nothing to commit"
                    then
                        echo "No image changes; nothing to commit"
                    else
                        git commit -am "Updating \${REPORT_FILE}"
                        if ${params.dry_run}
                        then
                            echo "Dry run; would have updated \${REPORT_FILE} with: \${REPORT_IMAGES}"
                        else
                            git push https://${env.GITHUB_CREDS_USR}:${env.GITHUB_CREDS_PSW}@github.com/charmed-kubernetes/bundle.git
                        fi
                    fi
                    cd -

                    echo "All images known to this builder:"
                    sudo lxc exec ${lxc_name} -- ctr image ls
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
                            sudo lxc shell ${lxc_name} -- bash -c "snapcraft login --with /snapcraft-creds"
                            for arch in ${env.ADDONS_ARCHES}
                            do
                                if [ "\${arch}" = "ppc64le" ]
                                then
                                    arch="ppc64el"
                                fi
                                BUILT_SNAP="cdk-addons_${kube_ersion}_\${arch}.snap"

                                echo "Uploading \${BUILT_SNAP}."
                                sudo lxc shell ${lxc_name} -- bash -c \
                                    "snapcraft -v upload /\${BUILT_SNAP} --release ${params.channels}"
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
