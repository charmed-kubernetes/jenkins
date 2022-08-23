@Library('juju-pipeline@master') _  // wokeignore:rule=master


pipeline {
    agent {
        label "runner-cloud"
    }
    environment {
        CDKBOT_GH            = credentials('cdkbot_github')
        GITHUB_TOKEN         = "${env.CDKBOT_GH_PSW}"
    }
    options {
        ansiColor('xterm')
        timestamps()
    }
    stages {
        stage("Checkout Docs Repository") {
            steps {
                checkout([
                    $class: 'GitSCM',
                    branches: [[name: env.BRANCH]],
                    doGenerateSubmoduleConfigurations: false,
                    extensions: [[$class: 'RelativeTargetDirectory', relativeTargetDir: 'kubernetes-docs']],
                    submoduleCfg: [],
                    userRemoteConfigs: [[url: "https://${CDKBOT_GH_USR}:${CDKBOT_GH_PSW}@github.com/charmed-kubernetes/kubernetes-docs.git"]]
                ])
            }
        }
        stage("Run Docs build") {
            steps {
                dir("kubernetes-docs/generator") {
                    sh(script: "tox -e run")
                }
            }
        }
        stage("Craft PR if Required") {
            steps {
                dir("kubernetes-docs") {
                    script {
                        def changes = sh(script: "git status -s", returnStdout: true).trim()
                        if (changes && env.DRY_RUN == "yes") {
                            echo "======= Changes detected during dry-run =========="
                            sh """git diff"""
                        }
                        else if ( changes != "") {
                            echo "======= Changes detected, crafting branch =========="
                            sh """
                            git config user.email ${CDKBOT_GH_USR}@gmail.com
                            git config user.name ${CDKBOT_GH_USR}
                            git config --global push.default simple
                            git checkout -b ${BUILD_TAG}
                            git add .
                            git commit -m "Updating Release Docs for ${RELEASE}"
                            git push --set-upstream origin ${BUILD_TAG}
                            """
                            echo "======= Branch Created ${BUILD_TAG} =========="
                        } else {
                            echo "====== No Changes detected =========="
                        }
                    }
                }
            }
        }
    }
}
