@Library('juju-pipeline@master') _

def to_channels = params.to_channel.split()
def charm_sh = "tox -e py36 -- python3 build-charms/charms.py"
def charms = [
    'containers/calico',
    'containers/canal',
    'containers/easyrsa',
    'containers/etcd',
    'containers/flannel',
    'containers/kubeapi-load-balancer',
    'containers/kubernetes-e2e',
    'containers/kubernetes-master',
    'containers/kubernetes-worker',
    'containers/keepalived',
    'containers/docker-registry',
    'containers/tigera-secure-ee',
    'containers/bundle/canonical-kubernetes',
    'containers/bundle/kubernetes-core',
    'containers/bundle/kubernetes-calico',
    'containers/bundle/canonical-kubernetes-canal',
    'kubeflow-charmers/kubeflow',
    'kubeflow-charmers/kubeflow-ambassador',
    'kubeflow-charmers/kubeflow-pytorch-operator',
    'kubeflow-charmers/kubeflow-seldon-api-frontend',
    'kubeflow-charmers/kubeflow-seldon-cluster-manager',
    'kubeflow-charmers/kubeflow-tf-hub',
    'kubeflow-charmers/kubeflow-tf-job-dashboard',
    'kubeflow-charmers/kubeflow-tf-job-operator',
    'kubeflow-charmers/kubeflow-tf-serving',
]

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
                                sh "${charm_sh} promote --charm-entity cs:~${charm} --from-channel ${params.from_channel} --to-channel ${channel}"
                                sh "${charm_sh} show --charm-entity cs:~${charm} --channel ${channel}"
                            }
                        }
                    }
                }
            }
        }
    }
}
