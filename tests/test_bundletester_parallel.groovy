def tests = ['test_bundletester']
def clouds = []
def bundles = ['kubernetes-core']

stage('Input Validation') {
    echo "CHARM_CHANNEL: "+CHARM_CHANNEL
    echo "SNAP_CHANNEL: "+SNAP_CHANNEL

    // Fill the clouds array
    if (CLOUD_AWS == "true") { clouds+="jenkins-ci-aws" }
    if (CLOUD_GCE == "true") { clouds+="jenkins-ci-google" }
    if (CLOUD_LXD == "true") { clouds+="jenkins-ci-lxd" }
}
stage('Testing') {
    def jobs = [:]

    for (int t = 0; t < tests.size(); t++) {
        def test = tests[t]
        for (int c = 0; c < clouds.size(); c++) {
            def cloud = clouds[c]
            def node = "juju-client"
            if (cloud == "jenkins-ci-lxd") {
                // lxd runs on its own machine
                node = "autolxd"
            }
            for (int b = 0; b < bundles.size(); b++) {
                def bundle = bundles[b]
                if (test == "test_bundletester" && bundle != 'kubernetes-core') {
                    continue
                }
                def job_name = (cloud+bundle+test).replace('_','').replace('-','')
                echo "Preparing job for "+test+" on "+bundle+" on "+cloud
                jobs[job_name] = {
                    stage(cloud+" "+bundle+" "+test) {
                        echo "Running "+job_name
                        build job: 'test-bundletester', parameters: [
                            string(name: 'TEST_CONTROLLER', value: cloud), 
                            string(name: 'CHARM_CHANNEL', value: CHARM_CHANNEL), 
                            string(name: 'SNAP_CHANNEL', value: SNAP_CHANNEL), 
                            string(name: 'TEST_BUNDLES', value: bundle), 
                            [$class: 'LabelParameterValue', name: 'NODE', label: node],
                            string(name: 'TEST_NAME', value: test)
                        ]
                    } 
                }
            }
        }
    }

    parallel jobs
}