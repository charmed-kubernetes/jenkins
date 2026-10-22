pipeline {
    agent {
        label "${params.build_node}"
    }
    /* XXX: Global $PATH setting doesn't translate properly in pipelines
     https://stackoverflow.com/questions/43987005/jenkins-does-not-recognize-command-sh
     */
    environment {
        // Jenkins env names are case-insensitive; avoid the versions/dry_run parameter names.
        CK_VERSIONS = "${params.versions}"
        IS_DRY_RUN = "${params.dry_run}"
        HOME = "/var/lib/jenkins"
        PATH = "/snap/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
        HTTP_PROXY = "http://egress.ps7.internal:3128"
        HTTPS_PROXY = "http://egress.ps7.internal:3128"
        http_proxy = "http://egress.ps7.internal:3128"
        https_proxy = "http://egress.ps7.internal:3128"
        NO_PROXY = "localhost,127.0.0.1"
        no_proxy = "localhost,127.0.0.1"
        DOCKERHUB_CREDS = credentials('cdkbot_dockerhub')
        GITHUB_CREDS = credentials('cdkbot_github')
        GHCR_CREDS = credentials('ghcr_canonical_cdk')
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
        stage('Update Image Lists') {
            steps {
                sh 'bash jobs/sync-oci-images/sync-oci-images.sh prepare'
            }
        }
        stage('Sync Images') {
            steps {
                sh 'bash jobs/sync-oci-images/sync-oci-images.sh sync'
            }
        }
        stage('Publish Image Lists') {
            steps {
                sh 'bash jobs/sync-oci-images/sync-oci-images.sh publish'
            }
        }
    }
    post {
        always {
            /* override sh since cilib.sh has some non POSIX bits. */
            sh '''#!/usr/bin/env bash
                . ${WORKSPACE}/cilib.sh

                echo Docker status
                ci_docker_status $DOCKERHUB_CREDS_USR $DOCKERHUB_CREDS_PSW
               '''
        }
    }
}
