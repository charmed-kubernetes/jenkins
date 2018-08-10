# Name

- **Job**: `validate.yaml`
- **Project Name**: `Validate`

# Description

Runs `test_cdk::test_validate` against a deployed CDK.

# Parameters

- **controller**: Juju controller to use
- **model**: Juju model to create
- **cloud**: Cloud to test against
- **version_overlay**: Bundle overlay defining which k8s versions to test.
- **bundle_channel**: Default bundle channel to validate from, Set to 'stable' if performing an upgrade test.

# Usage

Typically, the default created jobs handle the bundles, versions, and test validations.

# References

- See `Jenkinsfile`
