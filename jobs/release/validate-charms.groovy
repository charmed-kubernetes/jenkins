def requireParameter(String name, Object value) {
    if (value == null || value.toString().trim().isEmpty()) {
        error("${name} is required")
    }
}

// <track>/<risk>, e.g. 1.36/beta. prior_track.py and the snap install need it.
def requireTrackChannel(String name, Object value) {
    requireParameter(name, value)
    if (!(value.toString().trim() ==~ /^\d+\.\d+\/(edge|beta|candidate|stable)$/)) {
        error("${name} must look like 1.36/beta, got '${value}'")
    }
}

def validateCellParameters(Map cell, Map jobParameters) {
    requireParameter('juju_channel', jobParameters.jujuChannel)
    if (cell.scenario == 'bugfix') {
        requireTrackChannel('snap_version', jobParameters.snapVersion)
        requireParameter('charm_channel', jobParameters.charmChannel)
    } else if (cell.scenario == 'bugfix-upgrade') {
        requireTrackChannel('charm_channel', jobParameters.charmChannel)
        requireParameter('cloud', jobParameters.cloud)
    } else if (cell.scenario == 'release-upgrade') {
        requireTrackChannel('snap_version', jobParameters.snapVersion)
        requireParameter('cloud', jobParameters.cloud)
    } else {
        error("unsupported release validation scenario: ${cell.scenario}")
    }
}

// Blank selection runs every cell; otherwise only the named cells, so a rerun
// after a single failed cell does not repeat the cells that already passed.
def selectCells(Map cells, String requested) {
    String selection = requested?.trim()
    if (!selection) {
        return cells
    }
    Map selected = [:]
    for (String name : selection.split(/[\s,]+/)) {
        if (!cells.containsKey(name)) {
            error("unknown cell '${name}'; available: ${cells.keySet().join(' ')}")
        }
        selected[name] = cells[name]
    }
    return selected
}

def runValidation(String scenario) {
    if (scenario == 'bugfix') {
        sh(returnStatus: true, script: '''#!/bin/bash
            set -e
            : "${snap_version:?snap_version is required}"
            : "${charm_channel:?charm_channel is required}"
            JUJU_CHANNEL="${RELEASE_JUJU_CHANNEL:?juju_channel is required}" bash jobs/release/runner.sh validate bugfix "$snap_version" jammy "$charm_channel"
        ''')
    } else if (scenario == 'bugfix-upgrade') {
        sh(returnStatus: true, script: '''#!/bin/bash
            set -e
            : "${offset:?offset is required}"
            : "${series:?series is required}"
            : "${charm_channel:?charm_channel is required}"
            : "${cloud:?cloud is required}"
            JUJU_CHANNEL="${RELEASE_JUJU_CHANNEL:?juju_channel is required}" bash jobs/release/runner.sh validate bugfix-upgrade "$offset" "$series" "$charm_channel" "$cloud"
        ''')
    } else {
        sh(returnStatus: true, script: '''#!/bin/bash
            set -e
            : "${snap_version:?snap_version is required}"
            : "${offset:?offset is required}"
            : "${cloud:?cloud is required}"
            JUJU_CHANNEL="${RELEASE_JUJU_CHANNEL:?juju_channel is required}" bash jobs/release/runner.sh validate release-upgrade "$snap_version" "$offset" jammy "$cloud"
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
        Map jobParameters = [
            jujuChannel: params.juju_channel ?: '',
            snapVersion: params.snap_version ?: '',
            charmChannel: params.charm_channel ?: '',
            cloud: params.cloud ?: ''
        ]

        // Jenkins EnvVars folds case: JUJU_CHANNEL would retain the juju_channel key.
        // Use a distinct key here; each shell sets the runner's uppercase variable.
        withEnv([
            "WORKSPACE=${pwd()}",
            "LXC_NAME=${lxcName}",
            "JUJU_CONTROLLER=${controller}",
            "RELEASE_JUJU_CHANNEL=${jobParameters.jujuChannel}",
            "CELL_NAME=${cell.name}",
            "snap_version=${jobParameters.snapVersion}",
            "charm_channel=${jobParameters.charmChannel}",
            "cloud=${jobParameters.cloud}",
            "offset=${cell.offset ?: ''}",
            "series=${cell.series ?: ''}",
            "deploy_snap=${cell.deploySnap ?: ''}",
            'HOME=/var/lib/jenkins',
            'PATH=/snap/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin',
            'LC_ALL=C.UTF-8',
            'LANG=C.UTF-8',
        ]) {
            validateCellParameters(cell, jobParameters)
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
                            JUJU_CHANNEL="${RELEASE_JUJU_CHANNEL:?juju_channel is required}" bash jobs/release/runner.sh prepare
                        ''')
                    }
                }
                if (primaryStatus == 0) {
                    stage("${cell.name}: Prepare Python") {
                        primaryStatus = sh(returnStatus: true, script: '''#!/bin/bash
                            set -e
                            JUJU_CHANNEL="${RELEASE_JUJU_CHANNEL:?juju_channel is required}" bash jobs/release/runner.sh python
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
                        JUJU_CHANNEL="${RELEASE_JUJU_CHANNEL:?juju_channel is required}" bash jobs/release/runner.sh cleanup
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
                            cells = [:]
                            // offset N deploys the stable snap N tracks before snap_version
                            [1, 2].each { offset ->
                                String name = "release-upgrade-offset-${offset}-jammy-amd64"
                                cells[name] = [name: name, scenario: 'release-upgrade', offset: "${offset}"]
                            }
                            break
                        default:
                            error("unsupported release validation job: ${env.JOB_BASE_NAME}")
                    }
                    cells = selectCells(cells, params.cells as String)
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
