# Name

- **Job**: `validate.yaml`
- **Project Name**: `Validate`

# Description

Runs `test_cdk` against a deployed CDK.

# Parameters

- **controller**: Juju controller to use
- **model**: Juju model to create
- **cloud**: Cloud to test against
- **version_overlay**: Bundle overlay defining which k8s versions to test.

# Usage

Adding a new Kubernetes version to the test matrix:

```
 - job-group:
    name: validate
    version:
      - '1.9':
          version_overlay: 'jobs/validate/1.9-overlay.yaml'
      - '1.10':
          version_overlay: 'jobs/validate/1.10-overlay.yaml'
      - '1.11':
          version_overlay: 'jobs/validate/1.11-overlay.yaml'
      - '1.12':
          version_overlay: 'jobs/validate/1.12-overlay.yaml'
    jobs:
      - '{name}-cloud-{cloud}-v{version}':
          cloud: ['aws', 'google']
```

And `jobs/validate/1.12-overlay.yaml` would have the following:

```
applications:
  kubernetes-master:
    options:
      channel: 1.12/edge
  kubernetes-worker:
    options:
      channel: 1.12/edge
```

# References

- See `Jenkinsfile`
