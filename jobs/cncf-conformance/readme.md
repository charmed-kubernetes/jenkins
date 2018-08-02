# Name

- **Job**: `cncf-conformance.yaml`
- **Project Name**: `k8s-conformance`

# Description

Runs CNCF Conformance testing against stable release of Kubernetes.

# Parameters

- **bundle_revision**: Default Juju charmstore bundle revision containing the appropriate k8s release.
- **sonobuoy_version**: Version of Sonobuoy to download and run, this performs the actual conformance test.
- **model**: Juju model
- **controller**: Cloud (Or controller model if exists in CI) to run against
- **k8sver**: List of stable k8s versions to test against
- **cloud**: List of clouds to test against (ie. `['aws','google']`)

# Usage

## Adding new release

In the `job-group` under `jobs` add an additional item with the k8s version, bundle revision, and clouds to test against:

```
 - job-group:
     name: '{name}-tests'
     jobs:
       - '{name}-tests-{k8sver}':
           k8sver: 'v1.11.x'
           bundle_revision: '218'
           cloud: ['aws', 'google']
       - '{name}-tests-{k8sver}':
           k8sver: 'v1.12.x'
           bundle_revision: '2xx'
           cloud: ['aws', 'google']
```

# References

- https://github.com/cncf/k8s-conformance
