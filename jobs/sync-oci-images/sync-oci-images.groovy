@Library('juju-pipeline@master') _

def bundle_image_file = "./bundle/container-images.txt"
def kube_status = "stable"
def kube_version = params.k8s_tag
def kube_ersion = null
if (kube_version != "") {
    kube_ersion = kube_version.substring(1)
}
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
        DOCKERHUB_CREDS = credentials('cdkbot_dockerhub')
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
                    fi

                    echo "Getting bundle from main branch."
                    git clone https://github.com/charmed-kubernetes/bundle.git --branch main --depth 1
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
                    sudo lxc shell ${lxc_name} -- bash -c "apt-get install containerd -y"
                """
            }
        }
        stage('Build Image List'){
            steps {
                echo "Setting K8s version: ${kube_version} and K8s ersion: ${kube_ersion}"
                sh """
                    echo "Processing upstream images."
                    UPSTREAM_KEY=${kube_version}-upstream:
                    UPSTREAM_LINE=\$(cd cdk-addons && make KUBE_VERSION=${kube_version} upstream-images 2>/dev/null | grep ^\${UPSTREAM_KEY})

                    echo "Updating bundle with upstream images."
                    if grep -q ^\${UPSTREAM_KEY} ${bundle_image_file}
                    then
                        sed -i -e "s|^\${UPSTREAM_KEY}.*|\${UPSTREAM_LINE}|g" ${bundle_image_file}
                    else
                        echo \${UPSTREAM_LINE} >> ${bundle_image_file}
                    fi
                    sort -o ${bundle_image_file} ${bundle_image_file}

                    cd bundle
                    if git status | grep -qi "nothing to commit"
                    then
                        echo "No image changes; nothing to commit"
                    else
                        git commit -am "Updating \${UPSTREAM_KEY} images"
                        if ${params.dry_run}
                        then
                            echo "Dry run; would have updated ${bundle_image_file} with: \${UPSTREAM_LINE}"
                        else
                            git push https://${env.GITHUB_CREDS_USR}:${env.GITHUB_CREDS_PSW}@github.com/charmed-kubernetes/bundle.git
                        fi
                    fi
                    cd -
                """
            }
        }
        stage('Process CI Images'){
            steps {
                sh """
                    # We need jujud-operator in rocks so we can bootstrap k8s models on
                    # vsphere, but the image tag has the juju version baked in. Try to
                    # determine a good image based on the installed juju snap.
                    JUJUD_VER=\$(snap list juju | grep juju | awk '{print \$2}')

                    # Prime our image list with the jujud-op image
                    CI_IMAGES="docker.io/jujusolutions/jujud-operator:\$JUJUD_VER"

                    # Key from the bundle_image_file used to identify images for CI
                    CI_KEY=ci-static:

                    ARCHES="amd64 arm64 ppc64le s390x"
                    for arch in \${ARCHES}
                    do
                        ARCH_IMAGES=\$(grep -e \${CI_KEY} ${bundle_image_file} | sed -e "s|\${CI_KEY}||g" -e "s|{{ arch }}|\${arch}|g")
                        CI_IMAGES="\${CI_IMAGES} \${ARCH_IMAGES}"
                    done

                    # Clean up dupes by making a sortable list, uniq it, and turn it back to a string
                    CI_IMAGES=\$(echo "\${CI_IMAGES}" | xargs -n1 | sort -u | xargs)

                    # All CK CI images live under ./cdk in our registry
                    TAG_PREFIX=${env.REGISTRY_URL}/cdk

                    # Login to increase rate limit for dockerhub
                    which docker && docker login -u ${env.DOCKERHUB_CREDS_USR} -p ${env.DOCKERHUB_CREDS_PSW}

                    for i in \${CI_IMAGES}
                    do
                        # Skip images that we already host
                        if echo \${i} | grep -qi -e 'rocks.canonical.com'
                        then
                            continue
                        fi

                        # Pull upstream image
                        if ${params.dry_run}
                        then
                            echo "Dry run; would have pulled: \${i}"
                        else
                            # simple retry if initial pull fails
                            if ! sudo lxc exec ${lxc_name} -- ctr image pull \${i} --all-platforms >/dev/null
                            then
                                echo "Retrying pull"
                                sleep 5
                                sudo lxc exec ${lxc_name} -- ctr image pull \${i} --all-platforms >/dev/null
                            fi
                        fi

                        # Massage image names
                        RAW_IMAGE=\${i}
                        for repl in ${env.REGISTRY_REPLACE}
                        do
                            if echo \${RAW_IMAGE} | grep -qi \${repl}
                            then
                                RAW_IMAGE=\$(echo \${RAW_IMAGE} | sed -e "s|\${repl}||g")
                                break
                            fi
                        done

                        # Tag and push
                        if ${params.dry_run}
                        then
                            echo "Dry run; would have tagged: \${i}"
                            echo "Dry run; would have pushed: \${TAG_PREFIX}/\${RAW_IMAGE}"
                        else
                            sudo lxc exec ${lxc_name} -- ctr image tag \${i} \${TAG_PREFIX}/\${RAW_IMAGE}
                            # simple retry if initial push fails
                            if ! sudo lxc exec ${lxc_name} -- ctr image push \${TAG_PREFIX}/\${RAW_IMAGE} --user "${env.REGISTRY_CREDS_USR}:${env.REGISTRY_CREDS_PSW}" >/dev/null
                            then
                                echo "Retrying push"
                                sleep 5
                                sudo lxc exec ${lxc_name} -- ctr image push \${TAG_PREFIX}/\${RAW_IMAGE} --user "${env.REGISTRY_CREDS_USR}:${env.REGISTRY_CREDS_PSW}" >/dev/null
                            fi
                        fi

                        # Remove image now that we've pushed to keep our disk req low(ish)
                        if ${params.dry_run}
                        then
                            echo "Dry run; would have removed: \${i} \${TAG_PREFIX}/\${RAW_IMAGE}"
                        else
                            sudo lxc exec ${lxc_name} -- ctr image rm \${i} \${TAG_PREFIX}/\${RAW_IMAGE}
                        fi
                    done

                    # Make sure this worker doesn't stay logged in to dockerhub
                    which docker && docker logout
                """
            }
        }
        stage('Process K8s Images'){
            steps {
                sh """
                    # Keys from the bundle_image_file used to identify images per release
                    STATIC_KEY=v${params.version}-static:
                    UPSTREAM_KEY=${kube_version}-upstream:

                    ALL_IMAGES=""
                    ARCHES="amd64 arm64 ppc64le s390x"
                    for arch in \${ARCHES}
                    do
                        ARCH_IMAGES=\$(grep -e \${STATIC_KEY} -e \${UPSTREAM_KEY} ${bundle_image_file} | sed -e "s|\${STATIC_KEY}||g" -e "s|\${UPSTREAM_KEY}||g" -e "s|{{ arch }}|\${arch}|g" -e "s|{{ multiarch_workaround }}||g")
                        ALL_IMAGES="\${ALL_IMAGES} \${ARCH_IMAGES}"
                    done

                    # Clean up dupes by making a sortable list, uniq it, and turn it back to a string
                    ALL_IMAGES=\$(echo "\${ALL_IMAGES}" | xargs -n1 | sort -u | xargs)

                    # All CK images are staged under ./staging/cdk in our registry
                    TAG_PREFIX=${env.REGISTRY_URL}/staging/cdk

                    # Login to increase rate limit for dockerhub
                    which docker && docker login -u ${env.DOCKERHUB_CREDS_USR} -p ${env.DOCKERHUB_CREDS_PSW}

                    for i in \${ALL_IMAGES}
                    do
                        # Skip images that we already host
                        if echo \${i} | grep -qi -e 'rocks.canonical.com' -e 'image-registry.canonical.com'
                        then
                            continue
                        fi

                        # Pull upstream image
                        if ${params.dry_run}
                        then
                            echo "Dry run; would have pulled: \${i}"
                        else
                            # simple retry if initial pull fails
                            if ! sudo lxc exec ${lxc_name} -- ctr image pull \${i} --all-platforms >/dev/null
                            then
                                echo "Retrying pull"
                                sleep 5
                                sudo lxc exec ${lxc_name} -- ctr image pull \${i} --all-platforms >/dev/null
                            fi
                        fi

                        # Massage image names
                        RAW_IMAGE=\${i}
                        for repl in ${env.REGISTRY_REPLACE}
                        do
                            if echo \${RAW_IMAGE} | grep -qi \${repl}
                            then
                                RAW_IMAGE=\$(echo \${RAW_IMAGE} | sed -e "s|\${repl}||g")
                                break
                            fi
                        done

                        # Tag and push to staging area
                        if ${params.dry_run}
                        then
                            echo "Dry run; would have tagged: \${i}"
                            echo "Dry run; would have pushed: \${TAG_PREFIX}/\${RAW_IMAGE}"
                        else
                            sudo lxc exec ${lxc_name} -- ctr image tag \${i} \${TAG_PREFIX}/\${RAW_IMAGE}
                            # simple retry if initial push fails
                            if ! sudo lxc exec ${lxc_name} -- ctr image push \${TAG_PREFIX}/\${RAW_IMAGE} --user "${env.REGISTRY_CREDS_USR}:${env.REGISTRY_CREDS_PSW}" >/dev/null
                            then
                                echo "Retrying push"
                                sleep 5
                                sudo lxc exec ${lxc_name} -- ctr image push \${TAG_PREFIX}/\${RAW_IMAGE} --user "${env.REGISTRY_CREDS_USR}:${env.REGISTRY_CREDS_PSW}" >/dev/null
                            fi
                        fi

                        # Remove image now that we've pushed to keep our disk req low(ish)
                        if ${params.dry_run}
                        then
                            echo "Dry run; would have removed: \${i} \${TAG_PREFIX}/\${RAW_IMAGE}"
                        else
                            sudo lxc exec ${lxc_name} -- ctr image rm \${i} \${TAG_PREFIX}/\${RAW_IMAGE}
                        fi
                    done

                    # Make sure this worker doesn't stay logged in to dockerhub
                    which docker && docker logout
                """
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
