stage('charms') {
    def jobs = [:]
    
    charms_to_build = ['easyrsa', 'etcd', 'flannel', 'kubeapi-load-balancer', 
    'kubernetes-master', 'kubernetes-worker', 'kubernetes-e2e', 'calico', 'canal'
    ]
    
    charms_to_build.each { charm_name ->
        jobs[charm_name] = {
            stage(charm_name) {
                build job: 'build-and-release-' + charm_name, parameters: [
                    booleanParam(name: 'RUN_TESTS', value: true),
                    string(name: 'CLOUD', value: 'aws'),
                    booleanParam(name: 'RELEASE', value: true),
                ]
            }
        }
    }
    parallel jobs
}

stage('bundles') {
    build job: 'build-and-release-bundles', parameters: [
    	// not running tests here because it would run the same tests
	// we run immediately below in deploy_test
        booleanParam(name: 'RUN_TESTS', value: false),
    ]
}

stage('deploy_test') {
    build job: '1.10.x_Kubernetes AWS', parameters: [
        string(name: 'CHARM_CHANNEL', value: 'edge'),
        string(name: 'SNAP_CHANNEL', value: 'stable'),
        booleanParam(name: 'BUNDLE_KUBERNETES_CORE', value: true),
        booleanParam(name: 'BUNDLE_CANONICAL_KUBERNETES', value: false),
        booleanParam(name: 'BUNDLE_CANONICAL_KUBERNETES_NVIDIA', value: false),
        booleanParam(name: 'BUNDLE_CANONICAL_KUBERNETES_CANAL', value: false),
        string(name: 'UPGRADE_FROM_CHARM_CHANNEL', value: 'stable'),
        string(name: 'UPGRGADE_TO_CHARM_CHANNEL', value: 'edge'),
        string(name: 'UPGRADE_FROM_SNAP_CHANNEL', value: 'stable'),
        string(name: 'UPGRADE_TO_SNAP_CHANNEL', value: 'stable'),
    ]
}

stage('promote') {
    build job: 'promote-all-charms-and-bundles', parameters: [
        string(name: 'FROM_CHANNEL', value: 'edge'),
        string(name: 'TO_CHANNEL', value: 'beta'),
    ]
}
