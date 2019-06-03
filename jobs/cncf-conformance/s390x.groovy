@Library('juju-pipeline@master') _

def juju_model = String.format("%s-%s", params.model, uuid())
def juju_controller = String.format("%s-%s", params.controller, uuid())

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
                ssh(env.S390X, "mkdir -p /home/ubuntu/jenkins || true")
                scp(env.S390X, "jobs/validate-alt-arch/lxd-profile.yaml", "/home/ubuntu/jenkins/lxd-profile.yaml")
                ssh(env.S390X, "juju bootstrap ${params.cloud} ${juju_controller} --debug")
                ssh(env.S390X, "juju add-model -c ${juju_controller} ${juju_model}")
                ssh(env.S390X, "juju config -m ${juju_controller}:${juju_model} kubernetes-master allow-privileged=true")
                ssh(env.S390X, "juju config -m ${juju_controller}:${juju_model} kubernetes-worker allow-privileged=true")

                script {
                    def data = readYaml file: params.version_overlay
                    data['applications']['kubernetes-worker'].options.ingress = false
                    data['applications']['kubernetes-master']['options']['enable-metrics'] = false
                    data['applications']['kubernetes-master']['options']['enable-dashboard-addons'] = false
                    sh "rm ${params.version_overlay}"
                    writeYaml file: params.version_overlay, data: data
                    scp(params.version_overlay, "/home/ubuntu/jenkins/overlay.yaml")
                    ssh(env.S390X, "cat /home/ubuntu/jenkins/validate-alt-arch/lxd-profile.yaml | sed -e \"s/##MODEL##/${juju_model}/\" | sudo lxc profile edit juju-${juju_model}")
                }
                sh "charm pull cs:~containers/${params.bundle} --channel ${params.bundle_channel} ./bundle-to-test"
                scp(env.S390X, "./bundle-to-test", "/home/ubuntu/jenkins/bundle-to-test")

                ssh(env.S390X, "juju deploy -m ${juju_controller}:${juju_model} /home/ubuntu/jenkins/bundle-to-test --overlay /home/ubuntu/jenkins/overlay.yaml --channel ${params.bundle_channel}")
                ssh(env.S390X, "juju-wait -e ${juju_.controller}:${juju_model} -w -r3 -t14400")
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
            ssh("juju destroy-controller --destroy-all-models --destroy-storage -y ${juju_controller} || true")
        }
    }
}
