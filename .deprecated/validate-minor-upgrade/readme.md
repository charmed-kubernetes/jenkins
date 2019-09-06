# Name

- **Job**: `validate-minor-upgrade.yaml`
- **Project Name**: `Validate Minor Upgrade`

# Description

Deploys stable version of k8s, upgrades to latest edge, validates via `test_cdk`.

# Parameters

- **controller**: Juju controller to use
- **model**: Juju model to create
- **cloud**: Cloud to test against
- **version_overlay**: Bundle overlay defining which k8s versions to test.
- **upgrade_snap_channel**: Next minor revision to upgrade to from snap store.
- **bundle**: Default bundle to deploy

# Usage

Pass a previous stable minor revision and the latest edge minor revision you wish to upgrade to and validate.

# References

- See `Jenkinsfile`
