
def tests = []
def clouds = []
def bundles = []
def run_bt = false

stage('Input Validation') {
    echo "CLOUD_AWS: "+CLOUD_AWS
    echo "CLOUD_GCE: "+CLOUD_GCE
    echo "CLOUD_LXD: "+CLOUD_LXD
    echo "TEST_CHARM_CHANNEL: "+TEST_CHARM_CHANNEL
    echo "TEST_SNAP_CHANNEL: "+TEST_SNAP_CHANNEL
    echo "TEST_BUNDLES: "+TEST_BUNDLES
    echo "TESTS_NAMES: "+TESTS_NAMES

    // Fill bundles array
    bundles = TEST_BUNDLES.replace(' ','').split(',')

    // Fill tests array
    tests = TESTS_NAMES.replace(' ','').split(',')

    // Fill the clouds array
    if (CLOUD_AWS == "true") { clouds+="jenkins-ci-aws" }
    if (CLOUD_GCE == "true") { clouds+="jenkins-ci-google" }
    if (CLOUD_LXD == "true") { clouds+="jenkins-ci-lxd" }

    if (tests.contains("test_bundletester")) {
        echo "Bundletester tests reuqested"
        run_bt = true
    }
}
stage('Testing') {
    def jobs = [:]

    for (int t = 0; t < tests.size(); t++) {
        def test = tests[t]
        if (test == "test_bundletester") continue
        for (int c = 0; c < clouds.size(); c++) {
            def cloud = clouds[c]
            def node = "juju-client"
            if (cloud == "jenkins-ci-lxd") {
                // lxd runs on its own machine
                node = "lxdnode"
            }
            for (int b = 0; b < bundles.size(); b++) {
                def bundle = bundles[b]
                def job_name = (cloud+bundle+test).replace('_','').replace('-','')
                echo "Preparing job for "+test+" on "+bundle+" on "+cloud
                // jobs[job_name] = {
                    stage(cloud+" "+bundle+" "+test) {
                        echo "Running "+job_name
                        build job: 'test-cdk', parameters: [string(name: 'TEST_CONTROLLER', value: cloud), string(name: 'TEST_CHARM_CHANNEL', value: TEST_CHARM_CHANNEL), string(name: 'TEST_SNAP_CHANNEL', value: TEST_SNAP_CHANNEL), string(name: 'TEST_BUNDLES', value: bundle), [$class: 'NodeParameterValue', name: 'NODE', labels: [node], nodeEligibility: [$class: 'AllNodeEligibility']], string(name: 'TEST_NAME', value: test)]
                    } 
                // }
            }
        }
    }

    if (run_bt){
        def test = "test_bundletester"
        for (int c = 0; c < clouds.size(); c++) {
            def cloud = clouds[c]
            def node = "juju-client"
            if (cloud == "jenkins-ci-lxd") {
                // lxd runs on its own machine
                node = "lxdnode"
            }
            def job_name = (cloud+test).replace('_','').replace('-','')
            echo "Preparing job for "+test+" on "+cloud
            // jobs[job_name] = {
                stage(cloud+" "+test) {
                    echo "Running "+job_name
                    build job: 'test-cdk', parameters: [string(name: 'TEST_CONTROLLER', value: cloud), string(name: 'TEST_CHARM_CHANNEL', value: TEST_CHARM_CHANNEL), string(name: 'TEST_SNAP_CHANNEL', value: TEST_SNAP_CHANNEL), string(name: 'TEST_BUNDLES', value: "kubernetes-core"), [$class: 'NodeParameterValue', name: 'NODE', labels: [node], nodeEligibility: [$class: 'AllNodeEligibility']], string(name: 'TEST_NAME', value: test)]
                }
            // }
        }
    }

    // parallel jobs
}
