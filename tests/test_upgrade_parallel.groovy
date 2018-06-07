def clouds = []
def bundles = []

stage('Input Validation') {
    echo "UPGRADE_FROM_CHARM_CHANNEL: "+UPGRADE_FROM_CHARM_CHANNEL
    echo "UPGRADE_TO_CHARM_CHANNEL: "+UPGRADE_TO_CHARM_CHANNEL
    echo "UPGRADE_FROM_SNAP_CHANNEL: "+UPGRADE_FROM_SNAP_CHANNEL
    echo "UPGRADE_TO_SNAP_CHANNEL: "+UPGRADE_TO_SNAP_CHANNEL

    // Fill bundles array
    if (BUNDLE_KUBERNETES_CORE == "true") { bundles+="kubernetes-core" }
    if (BUNDLE_CANONICAL_KUBERNETES == "true") { bundles+="canonical-kubernetes" }
    if (BUNDLE_CANONICAL_KUBERNETES_NVIDIA == "true") { bundles+="canonical-kubernetes-nvidia" }
    if (BUNDLE_CANONICAL_KUBERNETES_CANAL == "true") { bundles+="canonical-kubernetes-canal" }

    // Fill the clouds array
    if (CLOUD_AWS == "true") { clouds+="jenkins-ci-aws" }
    if (CLOUD_GCE == "true") { clouds+="jenkins-ci-google" }
    if (CLOUD_LXD == "true") { clouds+="jenkins-ci-lxd" }
}
stage('Testing') {
    def jobs = [:]

    for (int c = 0; c < clouds.size(); c++) {
        def cloud = clouds[c]
        def node = "juju-client"
        if (cloud == "jenkins-ci-lxd") {
            // lxd runs on its own machine
            node = "autolxd"
        }
        for (int b = 0; b < bundles.size(); b++) {
            def bundle = bundles[b]
            def job_name = (cloud+bundle+"upgrade").replace('_','').replace('-','')
            echo "Preparing upgrade job for on "+bundle+" on "+cloud
            jobs[job_name] = {
                stage(cloud+" "+bundle+" upgrade") {
                    echo "Running "+job_name
                    build job: 'test-upgrade', parameters: [
                        string(name: 'TEST_CONTROLLER', value: cloud), 
                        string(name: 'UPGRADE_TO_CHARM_CHANNEL', value: UPGRADE_TO_CHARM_CHANNEL), 
                        string(name: 'UPGRADE_TO_SNAP_CHANNEL', value: UPGRADE_TO_SNAP_CHANNEL), 
                        string(name: 'UPGRADE_FROM_SNAP_CHANNEL', value: UPGRADE_FROM_SNAP_CHANNEL),
                        string(name: 'UPGRADE_FROM_CHARM_CHANNEL', value: UPGRADE_FROM_CHARM_CHANNEL),
                        string(name: 'TEST_BUNDLES', value: bundle), 
                        [$class: 'LabelParameterValue', name: 'NODE', label: node],
                    ]
                } 
            }
        }
    }

    parallel jobs
}