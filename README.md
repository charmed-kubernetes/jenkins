# Kubernetes Jenkins scripts

This project contains the scripts to build and test Kubernetes in Jenkins. 
These scripts assume Docker is installed on the Jenkins runner for isolation 
and limiting many package dependencies. Some of the scripts rely on
[Jenkins environment variables](https://wiki.jenkins-ci.org/display/JENKINS/Building+a+software+project)
but efforts have been made to be able to run the scripts locally (not on a
Jenkins server).

## jenkins_e2e.sh
Deploy a Kubernetes cluster with Juju and run the end to end (e2e) tests
against the cluster capturing the output. This script uses the `e2e-runner.sh`
to deploy the environment and run the tests, and `gubernator.sh` to upload the
results to a Google storage bucket which is published to Kubernetes.

## local_e2e.sh
The same as the `jenkins_e2e.sh` script but the ability to run it locally. This
script uses `export-local-env.sh` to set the Jenkins environment variables
before running.Ensure docker is installed and running on the local system 
before attempting to run this script.

# Usage
 1. Create a "Freestyle project" in Jenkins. 
 2. Select "Git" under Source Code Management section.
 3. Enter "https://github.com/juju-solutions/kubernetes-jenkins.git" in the
Repository URL field.
 4. Click on "Add a build step" in the Build section.
 5. Select "Execute shell"
 6. Enter a local path to the script you wish to use such as `./jenkins_e2e.sh`
 7. Save the script.
 8. Run the script.
