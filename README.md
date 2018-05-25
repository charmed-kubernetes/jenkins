# Kubernetes Jenkins scripts

This project contains the scripts used to build and test the CDK.

## What is where

 - under ./integration-tests: The set of tests used to validate a deployment.
   These test actual test cases are inside `validation.py`. To run them you
   will have to do so via pytest. To run the tests against an already running
   cluster you have to `pytest ./integration-tests/test_live_model.py`.
   To have the test setup a cluster for you do a `pytest ./integration-tests/test_cdk.py`  
 - under ./charm: Scripts to build and release all charms involved.
   The build and release process optionally includes running any
   bundletester tests.
 - under ./resources: Scripts to build charm resources.
 - under ./snaps: Scripts to build and release snaps.
