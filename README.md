# Kubernetes Jenkins scripts

This project contains the scripts used to build and test the CDK.

## What is where

 - *jobs* - All jenkins jobs housed here
 - *jobs/integration* - All integration tests housed here
 - *jobs/overlays* - All juju bundle overlays housed here.

## How to run tests locally

Running the tests locally can be accomplished easily with tox. The tests expect certain environment variables to be set. These can be found by looking at the Jenkinsfile for each test. For example, the [jobs/validate/Jenkinsfile](
https://github.com/juju-solutions/kubernetes-jenkins/blob/master/jobs/validate/Jenkinsfile) file has:

```
sh "CONTROLLER=${juju_controller} MODEL=${juju_model} CLOUD=${params.cloud} ${utils.pytest} --junit-xml=validate.xml integration/test_cdk.py::test_validate"
```

This tells us what the commandline is to run this test and what parameters we need to pass to it. These are passed to pytest running in tox. By default, the working directory for tox is in /var/lib/jenkins, which probably doesn't exist on development machines, so --workdir is used to specify a new directory to use.

```
CONTROLLER=aws-us-east-1 MODEL=cdk CLOUD=aws tox --workdir .tox -e py36 -- pytest -v -s --junit-xml=validate.xml integration/test_cdk.py::test_validate 2>&1 | tee ~/log.txt
```

## Developing new tests

Jenkins Job Builder is used to generate jobs for Jenkins programmatically. No jobs are created by hand in the Jenkins UI.

To add a new test into Jenkins, it is necessary to create a Jenkinsfile that is a script to run for the job and then a yaml file to describe the job to Jenkins Job Builder. Example job:

[validate Jenkinsfile](https://github.com/juju-solutions/kubernetes-jenkins/blob/master/jobs/validate/Jenkinsfile)

[validate yaml](https://github.com/juju-solutions/kubernetes-jenkins/blob/master/jobs/validate.yaml)
