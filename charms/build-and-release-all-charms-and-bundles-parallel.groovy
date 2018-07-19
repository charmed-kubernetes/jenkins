stage('charms') {
    def jobs = [:]

    charms_to_build = ['easyrsa', 'etcd', 'flannel', 'kubeapi-load-balancer',
    'kubernetes-master', 'kubernetes-worker', 'kubernetes-e2e', 'calico', 'canal'
    ]

    charms_to_build.each { charm_name ->
        jobs[charm_name] = {
            stage(charm_name) {
                build job: 'build-and-release-' + charm_name, parameters: [
                    booleanParam(name: 'RUN_TESTS', value: RUN_TESTS == "true"),
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
        booleanParam(name: 'RUN_TESTS', value: false),
    ]
}

stage('deploy_test') {
    if (RUN_TESTS == "true") {
        build job: 'test-cdk-parallel', parameters: [
            booleanParam(name: 'CLOUD_AWS', value: true),
            booleanParam(name: 'CLOUD_GCE', value: false),
            booleanParam(name: 'CLOUD_LXD', value: false),
            string(name: 'TEST_CHARM_CHANNEL', value: 'edge'),
            string(name: 'TEST_SNAP_CHANNEL', value: 'stable'),
            string(name: 'TEST_BUNDLES', value: 'canonical-kubernetes'),
            string(name: 'TESTS_NAMES', value: 'test_deploy, test_upgrade, test_bundletester')
        ]
    }
}

stage('promote') {
    if (RUN_TESTS == "true") {
        build job: 'promote-all-charms-and-bundles', parameters: [
            string(name: 'FROM_CHANNEL', value: 'edge'),
            string(name: 'TO_CHANNEL', value: 'beta'),
        ]
    }
}