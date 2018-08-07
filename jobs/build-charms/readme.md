# Name

- **Job**: `build-charms.yaml`
- **Project Name**: `build-release`

# Description

Builds and Releases all CDK related charms to their edge channels. Also performs
a simple `bundletester` on each charm prior to release.

# Parameters

- **charm**: Name of charm being built
- **from_channel**: Current channel charm sits in, typically 'unpublished' (default)
- **to_channel**: Where the charm is released, 'edge' (default)
- **model**: Juju model
- **controller**: Cloud (Or controller model if exists in CI) to run against
- **cloud**: List of clouds to test against (ie. `['aws','google']`)
- **repo_name**: Base name of git repo
- **git_repo**: Full path to git repo for upstream charm

# Usage

## Adding new charm

In the `job-group` under `jobs` add an additional item with the k8s version, snap overlay revision, and clouds to test against:

```
- job-group:
    name: '{name}'
    cloud: 'aws'
    charm:
      - 'vault':
          repo_name: 'layer-vault'
          git_repo: 'https://github.com/juju-solutions/{repo_name}.git'
    jobs:
      - '{name}-{charm}'
```

# References

- See `Jenkinsfile`
