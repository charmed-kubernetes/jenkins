@Library('juju-pipeline@master') _

def to_channels = params.to_channel.split()
def charm_sh = "tox -e py36 -- python3 build-charms/charms.py"
def charms = ['calico', 'canal', 'easyrsa', 'etcd',
              'flannel', 'kubeapi-load-balancer',
              'kubernetes-e2e', 'kubernetes-master',
              'kubernetes-worker', 'keepalived', 'docker-registry',
              'bundle/canonical-kubernetes', 'bundle/kubernetes-core',
              'bundle/kubernetes-calico', 'bundle/canonical-kubernetes-canal']

pipeline {
    agent { label 'runner-amd64' }
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
        stage('Release to Store') {
            options {
                timeout(time: 45, unit: 'MINUTES')
            }
            steps {
                dir('jobs') {
                    script {
                        charms.each { charm ->
                            to_channels.each { channel ->
                                sh "${charm_sh} promote --charm-entity cs:~containers/${charm} --from-channel ${params.from_channel} --to-channel ${channel}"
                                sh "${charm_sh} show --charm-entity cs:~containers/${charm} --channel ${channel}"
                            }
                        }
                    }
                }
            }
        }
    }
}
