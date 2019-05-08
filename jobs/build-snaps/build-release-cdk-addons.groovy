@Library('juju-pipeline@master') _

def snap_sh = "${utils.cipy} build-snaps/snaps.py"

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
        REGISTRY_URL = 'upload.image-registry.canonical.com:5000'

        KUBE_VERSION = """${sh(
            returnStdout: true,
            script: 'if "${params.k8s_tag}"; then echo "${params.k8s_tag}"; else echo $(curl -L https://dl.k8s.io/release/stable-${params.version}.txt); fi'
        )}"""
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
                sh "docker login -u ${env.REGISTRY_CREDS_USR} -p ${env.REGISTRY_CREDS_PSW} ${env.REGISTRY_URL}"
                sh "snapcraft login --with /var/lib/jenkins/snapcraft-creds"
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
                        echo "Creating \$ADDONS_BRANCH for cdk-addons."
                        git clone https://github.com/charmed-kubernetes/cdk-addons.git --depth 1
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
                """
                sh "git clone https://github.com/charmed-kubernetes/bundle.git"
            }
        }
        stage('Build cdk-addons and image list'){
            steps {
                sh """
                    echo "Building cdk-addons snap."
                    cd cdk-addons && make KUBE_ARCH=${params.arch} KUBE_VERSION=${env.KUBE_VERSION} default; cd -

                    echo "Processing upstream images."
                    IMAGES_FILE=./bundle/container-images.txt
                    UPSTREAM_KEY=${env.KUBE_VERSION}-upstream:
                    UPSTREAM_LINE=\$(cd cdk-addons && make KUBE_ARCH=${params.arch} KUBE_VERSION=${env.KUBE_VERSION} upstream-images 2>/dev/null | grep ^\${UPSTREAM_KEY}; cd -)

                    echo "Updating bundle with upstream images."
                    if grep -q ^\${UPSTREAM_KEY} \${IMAGES_FILE}
                    then
                        sed -i -e "s|^\${UPSTREAM_KEY}.*|\${UPSTREAM_LINE}|g" \${IMAGES_FILE}
                    else
                        echo \${UPSTREAM_LINE} >> \${IMAGES_FILE}
                    fi
                    sort -o \${IMAGES_FILE} \${IMAGES_FILE}
                    cd bundle
                    git commit -am "Updating \${UPSTREAM_KEY} images"
                    if ${params.dry_run}
                    then
                        echo "Dry run; would have pushed: \${UPSTREAM_LINE}"
                    else
                        git push https://${env.GITHUB_CREDS_USR}:${env.GITHUB_CREDS_PSW}@github.com/charmed-kubernetes/bundle.git
                    fi
                    cd -
                """
            }
        }
        stage('Push Images'){
            steps {
                sh """
                    IMAGES_FILE=./bundle/container-images.txt
                    STATIC_KEY=v${params.version}-static:
                    UPSTREAM_KEY=${env.KUBE_VERSION}-upstream:

                    echo "Pushing images to the Canonical registry"
                    ALL_IMAGES=\$(grep -e \${STATIC_KEY} -e \${UPSTREAM_KEY} \${IMAGES_FILE} | sed -e "s|\${STATIC_KEY}||g" -e "s|\${UPSTREAM_KEY}||g")
                    for i in \${ALL_IMAGES}
                    do
                        if ${params.dry_run}
                        then
                            echo "Dry run; would have pushed: \${i}"
                        fi
                    done
                """
            }
        }
        stage('Pushing cdk-addons'){
            steps {
                script {
                    if(params.dry_run) {
                        echo "Dry run; would have pushed cdk-addons/*.snap to ${params.version}/edge"
                    } else {
                        echo "snapcraft push cdk-addons/*.snap --release ${params.version}/edge"
                    }
                }
            }
        }
        stage('Promoting cdk-addons'){
            steps {
                script {
                    def snaps_to_release = ['cdk-addons']
                    params.channels.split().each { channel ->
                        snaps_to_release.each  { snap ->
                            if(params.dry_run) {
                                sh "${snap_sh} release --name ${snap} --channel ${channel} --version ${params.version} --dry-run"
                            } else {
                                sh "${snap_sh} release --name ${snap} --channel ${channel} --version ${params.version}"
                            }
                        }
                    }
                }
            }
        }
    }
    post {
        always {
            sh "sudo rm -rf cdk-addons/build"
            sh "docker image prune -a --filter \"until=24h\" --force"
            sh "docker container prune --filter \"until=24h\" --force"
            sh "docker logout ${env.REGISTRY_URL}"
            sh "snapcraft logout"
        }
    }
}
