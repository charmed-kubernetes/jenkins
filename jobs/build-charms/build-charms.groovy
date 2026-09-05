pipeline {
    agent {
        label 'amd64 && large'
    }
    options {
        ansiColor('xterm')
        timestamps()
        disableConcurrentBuilds()
    }
    environment {
        HOME                 = "/var/lib/jenkins"
        PATH                 = "/snap/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
        LC_ALL               = "C.UTF-8"
        LANG                 = "C.UTF-8"
        HTTP_PROXY           = "http://egress.ps7.internal:3128"
        HTTPS_PROXY          = "http://egress.ps7.internal:3128"
        http_proxy           = "http://egress.ps7.internal:3128"
        https_proxy          = "http://egress.ps7.internal:3128"
        NO_PROXY             = "localhost,127.0.0.1"
        no_proxy             = "localhost,127.0.0.1"
        PYTHONPATH           = "$WORKSPACE"
        TMPDIR               = "/tmp/$BUILD_TAG"
        CHARM_BASE_DIR       = "$WORKSPACE/.cache/charmbuild/$BUILD_TAG"
        CHARM_BUILD_DIR      = "$WORKSPACE/.cache/charmbuild/$BUILD_TAG/${params.CHARM_BUILD_DIR?.trim() ? params.CHARM_BUILD_DIR : 'build/charms'}"
        CHARM_LAYERS_DIR     = "$WORKSPACE/.cache/charmbuild/$BUILD_TAG/${params.CHARM_LAYERS_DIR?.trim() ? params.CHARM_LAYERS_DIR : 'build/layers'}"
        CHARM_INTERFACES_DIR = "$WORKSPACE/.cache/charmbuild/$BUILD_TAG/${params.CHARM_INTERFACES_DIR?.trim() ? params.CHARM_INTERFACES_DIR : 'build/interfaces'}"
        CHARM_CHARMS_DIR     = "$WORKSPACE/.cache/charmbuild/$BUILD_TAG/charms"
        CHARM_CACHE_DIR      = "$WORKSPACE/.cache/charmbuild/$BUILD_TAG/cache"
        charmcraft_lxc       = "${env.JOB_NAME}-${env.BUILD_NUMBER}"
        CHARMCRAFT_AUTH      = credentials('charmcraft_creds')
        LPCREDS              = credentials('launchpad_creds')
        CDKBOT_GH            = credentials('cdkbot_github')
    }
    stages {
        stage('Prepare Python') {
            steps {
                sh '''#!/bin/bash
                set -eux
                sudo chown -R jenkins:jenkins /var/lib/jenkins/.config/ || true
                rm -rf "$WORKSPACE/charms" || true
                rm -rf "$TMPDIR" && mkdir -p "$TMPDIR"
                rm -rf "$WORKSPACE/.cache/charmbuild" || true
                mkdir -p "$CHARM_BUILD_DIR" "$CHARM_LAYERS_DIR" "$CHARM_INTERFACES_DIR"
                python3 -m venv venv
                venv/bin/python -m pip install tox
                venv/bin/tox --recreate -e py --notest
                '''
            }
        }
        stage('Prepare Charmcraft Container') {
            steps {
                sh '''#!/bin/bash
                set -eux
                source "$WORKSPACE/jobs/build-charms/charmcraft-lib.sh"
                ci_lxc_delete "$JOB_NAME"
                ci_charmcraft_launch "$charmcraft_lxc"
                '''
            }
        }
        stage('Build Charms') {
            steps {
                script {
                    env.CHARM_BUILD_STATUS = sh(returnStatus: true, script: '''#!/bin/bash
                    set -eux
                    set +u
                    source .tox/py/bin/activate
                    set -u
                    IS_FORCE=""
                    if [[ $FORCE = "true" ]]; then IS_FORCE="--force"; fi
                    WITH_CHARM_BRANCH=""
                    if [[ -n ${CHARM_BRANCH:-} ]]; then WITH_CHARM_BRANCH="--charm-branch $CHARM_BRANCH"; fi
                    python jobs/build-charms/main.py build \
                      --charm-list "$CHARM_LIST" \
                      --to-channel "$TO_CHANNEL" \
                      --resource-spec "$RESOURCE_SPEC" \
                      --filter-by-tag "$FILTER_BY_TAG" \
                      --layer-index "$LAYER_INDEX" \
                      --layer-list "$LAYER_LIST" \
                      --layer-branch "$LAYER_BRANCH" \
                      $WITH_CHARM_BRANCH \
                      $IS_FORCE
                    ''').toString()
                }
            }
        }
        stage('Build Bundles') {
            steps {
                script {
                    env.BUNDLE_BUILD_STATUS = sh(returnStatus: true, script: '''#!/bin/bash
                    set -eux
                    set +u
                    source .tox/py/bin/activate
                    set -u
                    python jobs/build-charms/main.py build-bundles \
                      --to-channel "$TO_CHANNEL" \
                      --bundle-list "$BUNDLE_LIST" \
                      --bundle-branch "$BUNDLE_BRANCH" \
                      --filter-by-tag "$FILTER_BY_TAG"
                    ''').toString()
                }
            }
        }
        stage('Evaluate Result') {
            steps {
                script {
                    if (env.CHARM_BUILD_STATUS != '0' || env.BUNDLE_BUILD_STATUS != '0') {
                        error("Build commands failed: charms=${env.CHARM_BUILD_STATUS}, bundles=${env.BUNDLE_BUILD_STATUS}")
                    }
                }
            }
        }
    }
    post {
        always {
            script {
                if (fileExists('jobs/build-charms/charmcraft-lib.sh')) {
                    sh '''#!/bin/bash
                    set -eux
                    source "$WORKSPACE/jobs/build-charms/charmcraft-lib.sh"
                    ci_lxc_delete "$charmcraft_lxc"
                    '''
                }
            }
        }
    }
}
