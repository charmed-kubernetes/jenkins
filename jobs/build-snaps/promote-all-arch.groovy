@Library('juju-pipeline@master') _

pipeline {
    agent {
        label 'master'
    }
    /* XXX: Global $PATH setting doesn't translate properly in pipelines
     https://stackoverflow.com/questions/43987005/jenkins-does-not-recognize-command-sh
     */
    environment {
        PATH = "/snap/bin:/usr/sbin:/usr/bin:/sbin:/bin:/usr/local/bin"
    }
    options {
        ansiColor('xterm')
        timestamps()
    }
    stages {
        stage('Promote all arch snaps') {
            options {
                timeout(time: 3, unit: 'HOURS')
            }
            steps {
                script {
                    def jobs = [:]
                    def arches = ['amd64', 'arm64', 'ppc64le', 's390x']
                    arches.each { arch ->
                        jobs[arch] = {
                            stage(String.format("Promoting: %s", arch)) {
                                build job:"promote-snaps-${arch}",
                                    parameters: [string(name:'promote_from', value: params.promote_from),
                                                 string(name:'promote_to', value: params.promote_to)]
                            }
                        }
                    }
                    parallel jobs
                }
            }
        }
    }
}
