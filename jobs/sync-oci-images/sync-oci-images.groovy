@Library('juju-pipeline@master') _

def bundle_image_file = "./bundle/container-images.txt"
def kube_status = "stable"
def kube_version = params.k8s_tag
def kube_ersion = null
if (kube_version != "") {
    kube_ersion = kube_version.substring(1)
}

pipeline {
    agent {
        label "${params.build_node}"
    }
    /* XXX: Global $PATH setting doesn't translate properly in pipelines
     https://stackoverflow.com/questions/43987005/jenkins-does-not-recognize-command-sh
     */
    environment {
        BUNDLE_IMAGE_FILE = "${bundle_image_file}"
        IS_DRY_RUN = "${params.dry_run}"
        LXC_NAME = "${env.JOB_NAME}-${env.BUILD_NUMBER}"
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
                /* override sh for this step:

                 Needed because cilib.sh has some non POSIX bits.
                 */
                sh '''#!/usr/bin/env bash
                    . ${WORKSPACE}/cilib.sh

                    # Check rate limit; fail fast if we can't pull at least 50 images
                    STATUS=$(ci_docker_status $DOCKERHUB_CREDS_USR $DOCKERHUB_CREDS_PSW)

                    # The line we care about should look like this:
                    #   ratelimit-remaining: 191;w=21600
                    LIMIT=$(echo "${STATUS}" | grep -i remaining | grep -o '[0-9]*' | head -n1)
                    if [ "$IS_DRY_RUN" = true ] ; then
                        echo "We are not really going to pull"
                    elif [[ -n ${LIMIT} && ${LIMIT} -le 50 ]]; then
                        echo Docker Hub rate limit is too low
                        exit 1
                    else
                        # Either we didn't get a good limit, or it's seems big enough
                        echo Go for it!
                    fi

                    git config --global user.email "cdkbot@juju.solutions"
                    git config --global user.name "cdkbot"
                '''
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
            environment {
                ADDONS_BRANCH = "release-${params.version}"
            }
            steps {
                sh '''
                    if git ls-remote --exit-code --heads https://github.com/charmed-kubernetes/cdk-addons.git $ADDONS_BRANCH
                    then
                        echo "Getting cdk-addons from $ADDONS_BRANCH branch."
                        git clone https://github.com/charmed-kubernetes/cdk-addons.git --branch $ADDONS_BRANCH --depth 1
                    else
                        echo "Getting cdk-addons from default branch."
                        git clone https://github.com/charmed-kubernetes/cdk-addons.git --depth 1
                    fi

                    echo "Getting bundle from main branch."
                    git clone https://github.com/charmed-kubernetes/bundle.git --branch main --depth 1
                '''
            }
        }
        stage('Setup Build Container'){
            steps {
                /* override sh for this step:

                 Needed because cilib.sh has some non POSIX bits.
                 */
                sh '''#!/usr/bin/env bash
                    . ${WORKSPACE}/cilib.sh

                    ci_lxc_launch ubuntu:20.04 $LXC_NAME
                    sudo lxc shell $LXC_NAME -- bash -c "apt-get install containerd -y"
                   '''
            }
        }
        stage('Build Image List'){
            environment {
                KUBE_VERSION = "${kube_version}"
                KUBE_ERSION = "${kube_ersion}"
            }
            steps {
                echo "Setting K8s version: ${kube_version} and K8s ersion: ${kube_ersion}"
                sh '''
                    echo "Processing upstream images."
                    UPSTREAM_KEY=$KUBE_VERSION-upstream:
                    UPSTREAM_LINE=$(cd cdk-addons && make KUBE_VERSION=$KUBE_VERSION upstream-images 2>/dev/null | grep ^${UPSTREAM_KEY})

                    echo "Updating bundle with upstream images."
                    if grep -q ^${UPSTREAM_KEY} $BUNDLE_IMAGE_FILE
                    then
                        sed -i -e "s|^${UPSTREAM_KEY}.*|${UPSTREAM_LINE}|g" $BUNDLE_IMAGE_FILE
                    else
                        echo ${UPSTREAM_LINE} >> $BUNDLE_IMAGE_FILE
                    fi
                    sort -o $BUNDLE_IMAGE_FILE $BUNDLE_IMAGE_FILE

                    cd bundle
                    if git status | grep -qi "nothing to commit"
                    then
                        echo "No image changes; nothing to commit"
                    else
                        git commit -am "Updating ${UPSTREAM_KEY} images"
                        if [ "$IS_DRY_RUN" = true ] ; then
                            echo "Dry run; would have updated $BUNDLE_IMAGE_FILE with: ${UPSTREAM_LINE}"
                        else
                            git push https://$GITHUB_CREDS_USR:$GITHUB_CREDS_PSW@github.com/charmed-kubernetes/bundle.git
                        fi
                    fi
                    cd -
                   '''
            }
        }
        stage('Process CI Images'){
            steps {
                sh '''
                    # We need jujud-operator in rocks so we can bootstrap k8s models on
                    # vsphere, but the image tag has the juju version baked in. Try to
                    # determine a good image based on all the possible juju snaps.
                    JUJUD_VERS=$(snap info juju |grep -E '[0-9]{1,}\\.[0-9]{1,}\\.[0-9]{1,} '| awk '{print $2}')

                    # Prime our image list with the jujud-operator images
                    CI_IMAGES=""
                    for ver in ${JUJUD_VERS}
                    do
                        CI_IMAGES="${CI_IMAGES} docker.io/jujusolutions/jujud-operator:$ver"
                    done

                    # Key from the bundle_image_file used to identify images for CI
                    CI_KEY=ci-static:

                    ARCHES="amd64 arm64 ppc64le s390x"
                    for arch in ${ARCHES}
                    do
                        ARCH_IMAGES=$(grep -e ${CI_KEY} $BUNDLE_IMAGE_FILE | sed -e "s|${CI_KEY}||g" -e "s|{{ arch }}|${arch}|g")
                        CI_IMAGES="${CI_IMAGES} ${ARCH_IMAGES}"
                    done

                    # Clean up dupes by making a sortable list, uniq it, and turn it back to a string
                    CI_IMAGES=$(echo "${CI_IMAGES}" | xargs -n1 | sort -u | xargs)

                    # All CK CI images live under ./cdk in our registry
                    TAG_PREFIX=$REGISTRY_URL/cdk
                    PUSH_CREDS="-u $REGISTRY_CREDS_USR:$REGISTRY_CREDS_PSW"

                    pull_ctr () {
                        PULL_PROXY="http://squid.internal:3128"
                        sudo lxc exec $LXC_NAME \
                        --env HTTP_PROXY="${PULL_PROXY}" \
                        --env HTTPS_PROXY="${PULL_PROXY}" \
                        -- ctr content fetch ${PULL_CREDS} ${1} --all-platforms >/dev/null; 
                    }

                    push_ctr () {
                        sudo lxc exec $LXC_NAME \
                        -- ctr image push ${PUSH_CREDS} ${1} >/dev/null;
                    }

                    for i in ${CI_IMAGES}
                    do
                        # Skip images that we already host
                        if echo ${i} | grep -qi -e 'rocks.canonical.com'
                        then
                            continue
                        fi

                        # Authn dockerhub images
                        if echo ${i} | grep -qi -e 'docker.io'
                        then
                            PULL_CREDS="-u $DOCKERHUB_CREDS_USR:$DOCKERHUB_CREDS_PSW"
                        else
                            PULL_CREDS=
                        fi

                        # Pull upstream image
                        if [ "$IS_DRY_RUN" = true ]
                        then
                            echo "Dry run; would have pulled: ${i}"
                        else
                            # simple retry if initial pull fails
                            if ! pull_ctr ${i} ; then
                                echo "Retrying pull ${i}"
                                sleep 5
                                pull_ctr ${i}
                            fi
                        fi

                        # Massage image names
                        RAW_IMAGE=${i}
                        for repl in $REGISTRY_REPLACE
                        do
                            if echo ${RAW_IMAGE} | grep -qi ${repl}
                            then
                                RAW_IMAGE=$(echo ${RAW_IMAGE} | sed -e "s|${repl}||g")
                                break
                            fi
                        done

                        # Tag and push
                        if [ "$IS_DRY_RUN" = true ] ; then
                            echo "Dry run; would have tagged: ${i}"
                            echo "Dry run; would have pushed: ${TAG_PREFIX}/${RAW_IMAGE}"
                        else
                            sudo lxc exec $LXC_NAME -- ctr image tag ${i} ${TAG_PREFIX}/${RAW_IMAGE}
                            # simple retry if initial push fails
                            if ! push_ctr ${TAG_PREFIX}/${RAW_IMAGE}
                            then
                                echo "Retrying push"
                                sleep 5
                                push_ctr ${TAG_PREFIX}/${RAW_IMAGE}
                            fi
                        fi

                        # Remove image now that we've pushed to keep our disk req low(ish)
                        if [ "$IS_DRY_RUN" = true ] ; then
                            echo "Dry run; would have removed: ${i} ${TAG_PREFIX}/${RAW_IMAGE}"
                        else
                            sudo lxc exec $LXC_NAME -- ctr image rm ${i} ${TAG_PREFIX}/${RAW_IMAGE}
                        fi
                    done
                '''
            }
        }
        stage('Process K8s Images'){
            environment {
                // Keys from the bundle_image_file used to identify images per release
                STATIC_KEY = "v${params.version}-static:"
                UPSTREAM_KEY = "${kube_version}-upstream:"
            }
            steps {
                sh '''
                    ALL_IMAGES=""
                    ARCHES="amd64 arm64 ppc64le s390x"
                    for arch in ${ARCHES}
                    do
                        ARCH_IMAGES=$(grep -e $STATIC_KEY -e $UPSTREAM_KEY $BUNDLE_IMAGE_FILE | sed -e "s|$STATIC_KEY||g" -e "s|$UPSTREAM_KEY||g" -e "s|{{ arch }}|${arch}|g" -e "s|{{ multiarch_workaround }}||g")
                        ALL_IMAGES="${ALL_IMAGES} ${ARCH_IMAGES}"
                    done

                    # Clean up dupes by making a sortable list, uniq it, and turn it back to a string
                    ALL_IMAGES=$(echo "${ALL_IMAGES}" | xargs -n1 | sort -u | xargs)

                    # All CK images are staged under ./staging/cdk in our registry
                    TAG_PREFIX=$REGISTRY_URL/staging/cdk
                    PUSH_CREDS="-u $REGISTRY_CREDS_USR:$REGISTRY_CREDS_PSW"

                    pull_ctr () {
                        PULL_PROXY="http://squid.internal:3128"
                        sudo lxc exec $LXC_NAME \
                        --env HTTP_PROXY="${PULL_PROXY}" \
                        --env HTTPS_PROXY="${PULL_PROXY}" \
                        -- ctr content fetch ${PULL_CREDS} ${1} --all-platforms >/dev/null; 
                    }

                    push_ctr () {
                        sudo lxc exec $LXC_NAME \
                        -- ctr image push ${PUSH_CREDS} ${1} >/dev/null;
                    }

                    for i in ${ALL_IMAGES}
                    do
                        # Skip images that we already host
                        if echo ${i} | grep -qi -e 'rocks.canonical.com' -e 'image-registry.canonical.com'
                        then
                            continue
                        fi

                        # Authn dockerhub images
                        if echo ${i} | grep -qi -e 'docker.io'
                        then
                            PULL_CREDS="-u $DOCKERHUB_CREDS_USR:$DOCKERHUB_CREDS_PSW"
                        else
                            PULL_CREDS=
                        fi

                        # Pull upstream image
                        if [ "$IS_DRY_RUN" = true ] ; then
                            echo "Dry run; would have pulled: ${i}"
                        else
                            # simple retry if initial pull fails
                            if ! pull_ctr ${i}
                            then
                                echo "Retrying pull"
                                sleep 5
                                pull_ctr ${i}
                            fi
                        fi

                        # Massage image names
                        RAW_IMAGE=${i}
                        for repl in $REGISTRY_REPLACE
                        do
                            if echo ${RAW_IMAGE} | grep -qi ${repl}
                            then
                                RAW_IMAGE=$(echo ${RAW_IMAGE} | sed -e "s|${repl}||g")
                                break
                            fi
                        done

                        # Tag and push to staging area
                        if [ "$IS_DRY_RUN" = true ] ; then
                            echo "Dry run; would have tagged: ${i}"
                            echo "Dry run; would have pushed: ${TAG_PREFIX}/${RAW_IMAGE}"
                        else
                            sudo lxc exec $LXC_NAME -- ctr image tag ${i} ${TAG_PREFIX}/${RAW_IMAGE}
                            # simple retry if initial push fails
                            if ! push_ctr ${TAG_PREFIX}/${RAW_IMAGE}
                            then
                                echo "Retrying push"
                                sleep 5
                                push_ctr ${TAG_PREFIX}/${RAW_IMAGE}
                            fi
                        fi

                        # Remove image now that we've pushed to keep our disk req low(ish)
                        if [ "$IS_DRY_RUN" = true ] ; then
                            echo "Dry run=; would have removed: ${i} ${TAG_PREFIX}/${RAW_IMAGE}"
                        else
                            sudo lxc exec $LXC_NAME -- ctr image rm ${i} ${TAG_PREFIX}/${RAW_IMAGE}
                        fi
                    done
                   '''
            }
        }
    }
    post {
        always {
            /* override sh since cilib.sh has some non POSIX bits. */
            sh '''#!/usr/bin/env bash
                . ${WORKSPACE}/cilib.sh

                ci_lxc_delete $LXC_NAME
                sudo rm -rf cdk-addons/build

                echo Disk usage after cleanup
                df -h -x squashfs -x overlay | grep -vE ' /snap|^tmpfs|^shm'

                echo Docker status
                ci_docker_status $DOCKERHUB_CREDS_USR $DOCKERHUB_CREDS_PSW
               '''
        }
    }
}
