def requireParameter(String name, Object value) {
    if (value == null || value.toString().trim().isEmpty()) {
        error("${name} is required")
    }
}

def validateCellParameters(Map cell) {
    requireParameter('juju_channel', params.juju_channel)
    if (cell.scenario == 'bugfix') {
        requireParameter('snap_version', params.snap_version)
        requireParameter('charm_channel', params.charm_channel)
    } else if (cell.scenario == 'bugfix-upgrade') {
        requireParameter('charm_channel', params.charm_channel)
        requireParameter('cloud', params.cloud)
    } else if (cell.scenario == 'release-upgrade') {
        requireParameter('snap_version', params.snap_version)
        requireParameter('cloud', params.cloud)
    } else {
        error("unsupported release validation scenario: ${cell.scenario}")
    }
}

def runValidation(String scenario) {
    if (scenario == 'bugfix') {
        sh(returnStatus: true, script: '''#!/bin/bash
            set -e
            : "${snap_version:?snap_version is required}"
            : "${charm_channel:?charm_channel is required}"
            bash jobs/release/runner.sh validate bugfix "$snap_version" jammy "$charm_channel"
        ''')
    } else if (scenario == 'bugfix-upgrade') {
        sh(returnStatus: true, script: '''#!/bin/bash
            set -e
            : "${offset:?offset is required}"
            : "${series:?series is required}"
            : "${charm_channel:?charm_channel is required}"
            : "${cloud:?cloud is required}"
            bash jobs/release/runner.sh validate bugfix-upgrade "$offset" "$series" "$charm_channel" "$cloud"
        ''')
    } else {
        sh(returnStatus: true, script: '''#!/bin/bash
            set -e
            : "${snap_version:?snap_version is required}"
            : "${deploy_snap:?deploy_snap is required}"
            : "${cloud:?cloud is required}"
            bash jobs/release/runner.sh validate release-upgrade "$snap_version" "$deploy_snap" jammy "$cloud"
        ''')
    }
}

def runCell(Map cell) {
    node('amd64 && large') {
        withEnv([
            'HTTP_PROXY=http://egress.ps7.internal:3128',
            'HTTPS_PROXY=http://egress.ps7.internal:3128',
            'http_proxy=http://egress.ps7.internal:3128',
            'https_proxy=http://egress.ps7.internal:3128',
            'NO_PROXY=localhost,127.0.0.1',
            'no_proxy=localhost,127.0.0.1'
        ]) {
            deleteDir()
            checkout scm

        String token = UUID.randomUUID().toString()
        String lxcName = "release-${token}"
        String controller = "validate-${token}"
        int primaryStatus = 0
        int cleanupStatus = 0

        withEnv([
            "WORKSPACE=${pwd()}",
            "LXC_NAME=${lxcName}",
            "JUJU_CONTROLLER=${controller}",
            "JUJU_CHANNEL=${params.juju_channel ?: ''}",
            "CELL_NAME=${cell.name}",
            "snap_version=${params.snap_version ?: ''}",
            "charm_channel=${params.charm_channel ?: ''}",
            "cloud=${params.cloud ?: ''}",
            "offset=${cell.offset ?: ''}",
            "series=${cell.series ?: ''}",
            "deploy_snap=${cell.deploySnap ?: ''}",
            'HOME=/var/lib/jenkins',
            'PATH=/snap/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin',
            'LC_ALL=C.UTF-8',
            'LANG=C.UTF-8',
        ]) {
            validateCellParameters(cell)
            try {
                stage("${cell.name}: Prepare container") {
                    withCredentials([
                        file(credentialsId: 'juju_creds', variable: 'JUJUCREDS'),
                        file(credentialsId: 'juju_clouds', variable: 'JUJUCLOUDS'),
                        file(credentialsId: 'aws_creds', variable: 'AWSCREDS'),
                        file(credentialsId: 'sso_token', variable: 'SSOCREDS')
                    ]) {
                        primaryStatus = sh(returnStatus: true, script: '''#!/bin/bash
                            set -e
                            : "${JUJU_CHANNEL:?juju_channel is required}"
                            bash jobs/release/runner.sh prepare
                        ''')
                    }
                }
                if (primaryStatus == 0) {
                    stage("${cell.name}: Prepare Python") {
                        primaryStatus = sh(returnStatus: true, script: '''#!/bin/bash
                            set -e
                            bash jobs/release/runner.sh python
                        ''')
                    }
                }
                if (primaryStatus == 0) {
                    stage("${cell.name}: Validate") {
                        primaryStatus = runValidation(cell.scenario as String)
                    }
                }
            } finally {
                stage("${cell.name}: Cleanup") {
                    cleanupStatus = sh(returnStatus: true, script: '''#!/bin/bash
                        bash jobs/release/runner.sh cleanup
                    ''')
                }
            }
        }
        if (primaryStatus != 0) {
            error("${cell.name} validation failed with status ${primaryStatus}")
        }
        if (cleanupStatus != 0) {
            error("${cell.name} cleanup failed: ${cleanupStatus}")
        }
        }
    }
}

pipeline {
    agent none
    options {
        skipDefaultCheckout(true)
        disableConcurrentBuilds()
    }
    stages {
        stage('Validate combinations') {
            steps {
                script {
                    Map cells
                    switch (env.JOB_BASE_NAME) {
                        case 'validate-charm-bugfix':
                            cells = [
                                'bugfix-jammy-amd64': [name: 'bugfix-jammy-amd64', scenario: 'bugfix']
                            ]
                            break
                        case 'validate-charm-bugfix-upgrade':
                            cells = [:]
                            [0, 1, 2].each { offset ->
                                ['jammy', 'noble'].each { series ->
                                    String name = "bugfix-upgrade-offset-${offset}-${series}-amd64"
                                    cells[name] = [name: name, scenario: 'bugfix-upgrade', offset: "${offset}", series: series]
                                }
                            }
                            break
                        case 'validate-charm-release-upgrade':
                            cells = [
                                'release-upgrade-1-34-stable-jammy-amd64': [name: 'release-upgrade-1-34-stable-jammy-amd64', scenario: 'release-upgrade', deploySnap: '1.34/stable'],
                                'release-upgrade-1-33-stable-jammy-amd64': [name: 'release-upgrade-1-33-stable-jammy-amd64', scenario: 'release-upgrade', deploySnap: '1.33/stable']
                            ]
                            break
                        default:
                            error("unsupported release validation job: ${env.JOB_BASE_NAME}")
                    }
                    Map branches = [:]
                    cells.each { name, cell ->
                        branches[name] = {
                            catchError(buildResult: 'FAILURE', stageResult: 'FAILURE', catchInterruptions: false) {
                                runCell(cell)
                            }
                        }
                    }
                    parallel branches
                }
            }
        }
    }
}
