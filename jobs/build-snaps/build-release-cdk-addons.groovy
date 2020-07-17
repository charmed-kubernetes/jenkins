@Library('juju-pipeline@master') _

def bundle_image_file = "./bundle/container-images.txt"
def kube_status = "stable"
def kube_version = params.k8s_tag
def kube_ersion = null
def lxd_exec(String container, String cmd) {
    sh "sudo lxc exec ${container} -- bash -c '${cmd}'"
}

pipeline {
    agent {
        label "${params.build_node}"
    }
    /* XXX: Global $PATH setting doesn't translate properly in pipelines
     https://stackoverflow.com/questions/43987005/jenkins-does-not-recognize-command-sh
     */
    environment {
        PATH = "${utils.cipaths}"
        GITHUB_CREDS = credentials('cdkbot_github')
        REGISTRY_CREDS = credentials('canonical_registry')
        REGISTRY_URL = 'upload.rocks.canonical.com:5000'
        REGISTRY_REPLACE = 'docker.io/ k8s.gcr.io/ quay.io/'
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
                sh "snapcraft login --with /var/lib/jenkins/snapcraft-creds"
                sh "snapcraft whoami"
                sh "sudo chown jenkins:jenkins -R /var/lib/jenkins/.config/snapcraft"
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
                echo "Set K8s version to: ${kube_version} and K8s ersion: ${kube_ersion}"
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
                        echo "Getting cdk-addons from master branch."
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
        stage('Build cdk-addons and image list'){
            steps {
                sh """

                    cd cdk-addons
                    make KUBE_VERSION=${kube_version} prep
                    ARCHES="amd64 arm64 ppc64le s390x"
                    for arch in \${ARCHES}
                    do
                        echo "Building cdk-addons snap for arch \${arch}."
                	wget -O build/kubectl https://storage.googleapis.com/kubernetes-release/release/${kube_version}/bin/linux/\${arch}/kubectl
                	chmod +x build/kubectl
                	sed 's/KUBE_VERSION/${kube_ersion}/g' cdk-addons.yaml > build/snapcraft.yaml
                        if [ "\${arch}" = "ppc64le" ]
                        then
                          sed -i "s/KUBE_ARCH/ppc64el/g" build/snapcraft.yaml
                          cd build
                          SNAPCRAFT_BUILD_ENVIRONMENT=host snapcraft clean || exit 1
                          SNAPCRAFT_BUILD_ENVIRONMENT=host snapcraft --target-arch=ppc64el || exit 1
                          mv *.snap ..
                          cd ..
                        else
                          sed -i "s/KUBE_ARCH/\${arch}/g" build/snapcraft.yaml
                          cd build
                          SNAPCRAFT_BUILD_ENVIRONMENT=host snapcraft clean || exit 1
                          SNAPCRAFT_BUILD_ENVIRONMENT=host snapcraft --target-arch=\${arch} || exit 1
                          mv *.snap ..
                          cd ..
                        fi
                    done
                    cd ..

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
        stage('Setup LXD container for ctr'){
            steps {
                sh "sudo lxc launch ubuntu:18.04 image-processor"
                lxd_exec("image-processor", "sleep 5")
                lxd_exec("image-processor", "apt update")
                lxd_exec("image-processor", "apt install containerd -y")
            }
        }
        stage('Process Images'){
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

                    # clean up dupes by making a sortable list, uniq it, and turn it back to a string
                    ALL_IMAGES=\$(echo "\${ALL_IMAGES}" | xargs -n1 | sort -u | xargs)

                    # All CK images are stored under ./cdk in our registry
                    TAG_PREFIX=${env.REGISTRY_URL}/cdk

                    for i in \${ALL_IMAGES}
                    do
                        # Skip images that we already host
                        if echo \${i} | grep -qi -e 'rocks.canonical.com' -e 'image-registry.canonical.com'
                        then
                            continue
                        fi

                        # Skip images that dont exist (usually due to non-existing arch). Other
                        # pull failures will manifest themselves when we attempt to tag.
                        if sudo lxc exec image-processor -- ctr image pull \${i} --all-platforms 2>&1 | grep -qi 'not found'
                        then
                            continue
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
                        until sudo lxc exec image-processor -- ctr image tag \${i} \${TAG_PREFIX}/\${RAW_IMAGE}; do sleep 1; done
                        if ${params.dry_run}
                        then
                            echo "Dry run; would have pushed: \${TAG_PREFIX}/\${RAW_IMAGE}"
                        else
                            sudo lxc exec image-processor -- ctr image push \${TAG_PREFIX}/\${RAW_IMAGE} --user "${env.REGISTRY_CREDS_USR}:${env.REGISTRY_CREDS_PSW}"
                        fi
                    done

                    echo "All images known to this builder:"
                    sudo lxc exec image-processor -- ctr image ls
                """
            }
        }
        stage('Push cdk-addons snap'){
            steps {
                script {
                    if(params.dry_run) {
                        echo "Dry run; would have pushed cdk-addons/*.snap to ${params.channels}"
                    } else {
                        sh "snapcraft push cdk-addons/cdk-addons_${kube_ersion}_amd64.snap --release ${params.channels}"
                        sh "snapcraft push cdk-addons/cdk-addons_${kube_ersion}_arm64.snap --release ${params.channels}"
                        sh "snapcraft push cdk-addons/cdk-addons_${kube_ersion}_ppc64el.snap --release ${params.channels}"
                        sh "snapcraft push cdk-addons/cdk-addons_${kube_ersion}_s390x.snap --release ${params.channels}"
                    }
                }
            }
        }
    }
    post {
        always {
            sh "sudo lxc delete -f image-processor"
            sh "sudo rm -rf cdk-addons/build"
            sh "docker image prune -a --filter \"until=24h\" --force"
            sh "docker container prune --filter \"until=24h\" --force"
            sh "snapcraft logout"
        }
    }
}
