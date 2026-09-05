pipeline {
    agent {
        label 'amd64 && large'
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
        CHARM_BUILD_DIR      = "$WORKSPACE/.cache/charmbuild/$BUILD_TAG/build/charms"
        CHARM_LAYERS_DIR     = "$WORKSPACE/.cache/charmbuild/$BUILD_TAG/build/layers"
        CHARM_INTERFACES_DIR = "$WORKSPACE/.cache/charmbuild/$BUILD_TAG/build/interfaces"
        CHARM_CHARMS_DIR     = "$WORKSPACE/.cache/charmbuild/$BUILD_TAG/charms"
        CHARM_CACHE_DIR      = "$WORKSPACE/.cache/charmbuild/$BUILD_TAG/cache"
        CHARMCRAFT_AUTH      = credentials('charmcraft_creds')
    }
    stages {
        stage('Prepare Python') {
            steps {
                sh '''#!/bin/bash
                set -eux
                rm -rf "$TMPDIR" && mkdir -p "$TMPDIR"
                rm -rf "$WORKSPACE/.cache/charmbuild" || true
                mkdir -p "$CHARM_BUILD_DIR" "$CHARM_LAYERS_DIR" "$CHARM_INTERFACES_DIR"
                python3 -m venv venv
                venv/bin/python -m pip install tox
                venv/bin/tox --recreate -e py --notest
                '''
            }
        }
        stage('Promote Bundles') {
            steps {
                sh '''#!/bin/bash
                set -eux
                set +u
                source .tox/py/bin/activate
                set -u
                python jobs/build-charms/main.py promote \
                  --to-channel "$TO_CHANNEL" \
                  --from-channel "$FROM_CHANNEL" \
                  --charm-list "$BUNDLE_LIST" \
                  --filter-by-tag "$FILTER_BY_TAG"
                '''
            }
        }
    }
}
