# Name

- **Job**: `build-bundles.yaml`
- **Project Name**: `build-bundles`

# Description

Builds and Releases all CDK related bundles to their edge channels.

# Parameters

- **channel**: Where the bundle is released, 'edge' (default)
- **bundle_repo**: Full path to bundle-canonical-kubernetes

# Usage

## Adding new bundle

If new fragments are added into the bundle-canonical-kubernetes repo, then in
the `Jenkinsfile` under `Build` and `Release` stages, add the new bundle
build/release commands.

# References

- See `Jenkinsfile`
