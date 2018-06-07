def clouds = []
def bundles = []

stage('Input Validation') {
    echo "CHARM_CHANNEL: "+CHARM_CHANNEL
    echo "SNAP_CHANNEL: "+SNAP_CHANNEL

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
            def job_name = (cloud+bundle+"deploy").replace('_','').replace('-','')
            echo "Preparing deploy job for "+bundle+" on "+cloud
            jobs[job_name] = {
                stage(cloud+" "+bundle+" deploy") {
                    echo "Running "+job_name
                    build job: 'test-deploy', parameters: [
                        string(name: 'TEST_CONTROLLER', value: cloud), 
                        string(name: 'CHARM_CHANNEL', value: CHARM_CHANNEL), 
                        string(name: 'SNAP_CHANNEL', value: SNAP_CHANNEL), 
                        string(name: 'TEST_BUNDLES', value: bundle), 
                        [$class: 'LabelParameterValue', name: 'NODE', label: node]
                    ]
                } 
            }
        }
    }

    parallel jobs
}