# Name

- **Job**: `validate-nvidia.yaml`
- **Project Name**: `Validate-nvidia`

# Description

Runs `test_cdk::test_validate` against a deployed CDK on nvidia hardware.

# Parameters

- **controller**: Juju controller to use, has to be a controller on aws
- **model**: Juju model to create
- **overlay**: Bundle overlay defining which k8s versions and nvidia instance.
- **bundle_channel**: Default bundle channel to validate from, Set to 'stable' if performing an upgrade test.

# Usage

Typically, the default created jobs handle the bundles, versions, and test validations.

# References

- See `Jenkinsfile`
