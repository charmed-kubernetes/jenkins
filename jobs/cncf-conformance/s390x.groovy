@Library('juju-pipeline@master') _

def juju_model = String.format("%s-%s", params.model, uuid())
def juju_controller = String.format("%s-%s", params.controller, uuid())
def juju_sh = "/snap/bin/juju"

pipeline {
    agent {
        label 'runner-amd64'
    }
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
        stage("Deploy") {
            options {
                timeout(time: 4, unit: 'HOURS')
            }
            steps {
                setStartTime()
                ssh("s3lp3", "mkdir -p /home/ubuntu/jenkins || true")
                ssh("s3lp3", "git clone https://git.launchpad.net/juju-wait /home/ubuntu/jenkins/juju-wait || true")
                ssh("s3lp3", "sudo mv /home/ubuntu/jenkins/juju-wait/juju_wait/__init__.py /usr/local/bin/juju-wait && chmod 0777 /usr/local/bin/juju-wait || true")
                scp("s3lp3", "jobs/validate-alt-arch/lxd-profile.yaml", "/home/ubuntu/jenkins/lxd-profile.yaml")
                ssh("s3lp3", "${juju_sh} bootstrap ${params.cloud} ${juju_controller} --debug")
                ssh("s3lp3", "${juju_sh} add-model -c ${juju_controller} ${juju_model}")
                script {
                    def data = readYaml file: params.version_overlay
                    data['applications']['kubernetes-worker'].options.ingress = false
                    data['applications']['kubernetes-master']['options']['enable-metrics'] = false
                    data['applications']['kubernetes-master']['options']['enable-dashboard-addons'] = false
                    writeYaml file: "${params.version_overlay}-new", data: data
                }
                scp("s3lp3", "${params.version_overlay}-new", "/home/ubuntu/jenkins/overlay.yaml")
                ssh("s3lp3", "cat /home/ubuntu/jenkins/lxd-profile.yaml | sed -e \"s/##MODEL##/${juju_model}/\" | sudo lxc profile edit juju-${juju_model}")

                sh "charm pull cs:~containers/${params.bundle} --channel ${params.bundle_channel} ./bundle-to-test"
                scp("s3lp3", "./bundle-to-test", "/home/ubuntu/jenkins/bundle-to-test")

                ssh("s3lp3", "${juju_sh} deploy -m ${juju_controller}:${juju_model} /home/ubuntu/jenkins/bundle-to-test --overlay /home/ubuntu/jenkins/overlay.yaml --channel ${params.bundle_channel}")
                ssh("s3lp3", "${juju_sh} config -m ${juju_controller}:${juju_model} kubernetes-master allow-privileged=true || true")
                ssh("s3lp3", "${juju_sh} config -m ${juju_controller}:${juju_model} kubernetes-worker allow-privileged=true || true")
                ssh("s3lp3", "PATH=$PATH:/snap/bin /usr/local/bin/juju-wait -e ${juju_controller}:${juju_model} -w -r3 -t14400")
            }
        }
        // stage('Run: sonobuoy') {
        //     options {
        //         timeout(time: 3, unit: 'HOURS')
        //     }
        //     steps {
        //         runSonobuoy(juju_controller, juju_model)
        //     }
        // }
        // stage('Test') {
        //     options {
        //         timeout(time: 3, unit: 'HOURS')
        //     }
        //     steps {
        //         waitUntil {
        //             sh '/var/lib/jenkins/go/bin/sonobuoy status || true'
        //             script {
        //                 def r = sh script:'/var/lib/jenkins/go/bin/sonobuoy status|grep -q \'Sonobuoy has completed\'', returnStatus: true
        //                 return (r == 0);
        //             }
        //         }
        //     }
        // }
        // stage('Archive') {
        //     steps {
        //         waitUntil {
        //             script {
        //                 def r = sh script:'/var/lib/jenkins/go/bin/sonobuoy retrieve results/.', returnStatus: true
        //                 return (r == 0);
        //             }
        //         }
        //         archiveArtifacts artifacts: 'results/*.tar.gz'
        //     }
        // }
    }
    post {
        success {
            setPass()
        }
        failure {
            setFail()
        }
        cleanup {
            ssh("s3lp3", "${juju_sh} destroy-controller --destroy-all-models --destroy-storage -y ${juju_controller} || true")
        }
    }
}
