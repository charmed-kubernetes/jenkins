@Library('juju-pipeline@master') _
pipeline {
    agent { label "runner-cloud" }
    environment {
        PATH = "${utils.cipaths}"
        GIT_SSH_COMMAND='ssh -i /var/lib/jenkins/.ssh/cdkbot_rsa -oStrictHostKeyChecking=no'
        CDKBOT_GH = credentials('cdkbot_github')
    }
    options {
        ansiColor('xterm')
        timestamps()
    }
    stages {
        stage('Create snap recipes'){
            steps {
                dir('jobs'){
                    sh 'git ls-remote -t --refs https://github.com/kubernetes/kubernetes|sort -t "/" -k 3 -V | sed -E "s/^[[:xdigit:]]+[[:space:]]+refs\\/tags\\/(.+)/\\1/g" > includes/k8s-upstream-versions.inc'
                    sh 'git checkout master'
                    sh 'git config user.name cdkbot'
                    sh 'git config user.email cdkbot@gmail.com'
                    sh 'git add includes/k8s-upstream-versions.inc'
                    sh 'git commit -asm "Update release list"'
                    sh 'git push https://${CDKBOT_GH}@github.com/charmed-kubernetes/jenkins master'
                }
            }
        }
    }
}
