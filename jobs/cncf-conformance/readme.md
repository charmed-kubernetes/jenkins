# Name

- **Job**: `cncf-conformance.yaml`
- **Project Name**: `k8s-conformance`

# Description

Runs CNCF Conformance testing against releases of Kubernetes. These tests are
the baseline for downstream testing and releasing of CDK. These tests must pass
before the process of releasing to beta, candidate, and finally stable can
occur.

# Parameters

- **version_overlay**: Juju bundle file containing the snap revision/track to test against.
- **sonobuoy_version**: Version of Sonobuoy to download and run, this performs the actual conformance test.
- **model**: Juju model
- **controller**: Cloud (Or controller model if exists in CI) to run against
- **k8sver**: List of stable k8s versions to test against
- **cloud**: List of clouds to test against (ie. `['aws','google']`)
- **bundle_channel**: Bundle channel to use for deployment

# Usage

## Adding new release

In the `job-group` under `jobs` add an additional item with the k8s version, snap overlay revision, and clouds to test against:

```
- job-group:
    name: '{name}-tests'
    k8sver:
      - 'v1.12.x':
          version_overlay: '1.12-edge-overlay.yaml'
      - 'v1.11.x':
          version_overlay: '1.11-edge-overlay.yaml'
      - 'v1.10.x':
          version_overlay: '1.10-edge-overlay.yaml'
    jobs:
      - '{name}-tests-{k8sver}-{cloud}':
          cloud: ['aws', 'google']
```

An example of the overlay:
```
applications:
  kubernetes-master:
    charm: cs:~containers/kubernetes-master
    constraints: cores=2 mem=4G root-disk=16G
    num_units: 2
    options:
      channel: 1.12/edge
  kubernetes-worker:
    charm: cs:~containers/kubernetes-worker
    constraints: cores=4 mem=4G root-disk=16G
    expose: true
    num_units: 3
    options:
      channel: 1.12/edge
```



# References

- https://github.com/cncf/k8s-conformance
