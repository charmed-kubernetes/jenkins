@Library('juju-pipeline@master') _

def to_channels = params.to_channel.split()
def charm_sh = "${utils.cipy} build-charms/charms.py"

pipeline {
    agent { label 'runner-amd64' }
    /* XXX: Global $PATH setting doesn't translate properly in pipelines
     https://stackoverflow.com/questions/43987005/jenkins-does-not-recognize-command-sh
     */
    environment {
        PATH = "${utils.cipaths}"
    }
    options {
        ansiColor('xterm')
        timestamps()
    }
    stages {
        stage('Release K8S charms to Store') {
            when {
                expression {
                    return params.only_namespace == 'containers' || params.only_namespace == 'all'
                }
            }
            options {
                timeout(time: 45, unit: 'MINUTES')
            }
            steps {
                dir('jobs') {
                    script {
                        def jobs = [:]
                        // returns a LinkedHashMap
                        def charms = readYaml file: 'includes/charm-support-matrix.inc'
                        charms.each { k ->
                            // Each item is a LinkedHashSet, so we pull the first item from the set
                            // since there is only 1 key per charm
                            def charm = k.keySet().first()
                            if (k[charm].namespace != 'containers') {
                                return
                            }

                            jobs[charm] = {
                                to_channels.each { channel ->
                                    sh "${charm_sh} promote --charm-entity cs:~${k[charm].namespace}/${charm} --from-channel ${params.from_channel} --to-channel ${channel}"
                                    sh "${charm_sh} show --charm-entity cs:~${k[charm].namespace}/${charm} --channel ${channel}"
                                }
                            }
                        }
                        parallel jobs
                    }
                }
            }
        }
        stage('Release K8S extras to Store') {
            when {
                expression {
                    return params.only_namespace == 'kubeflow' || params.only_namespace == 'all'
                }
            }
            options {
                timeout(time: 45, unit: 'MINUTES')
            }
            steps {
                dir('jobs') {
                    script {
                        def jobs = [:]
                        // returns a LinkedHashMap
                        def charms = readYaml file: 'includes/charm-support-matrix.inc'
                        charms.each { k ->
                            // Each item is a LinkedHashSet, so we pull the first item from the set
                            // since there is only 1 key per charm
                            def charm = k.keySet().first()

                            if(k[charm].namespace != 'kubeflow') {
                                return
                            }

                            jobs[charm] = {
                                to_channels.each { channel ->
                                    sh "${charm_sh} promote --charm-entity cs:~${k[charm].namespace}/${charm} --from-channel ${params.from_channel} --to-channel ${channel}"
                                    sh "${charm_sh} show --charm-entity cs:~${k[charm].namespace}/${charm} --channel ${channel}"
                                }
                            }
                        }
                        parallel jobs
                    }
                }
            }
        }

    }
}
