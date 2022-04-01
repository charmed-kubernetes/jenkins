# Building Charms

The [build job][] in Jenkins builds charms from repos in the
[charmed-kubernetes org][] on GitHub. Charms with an upstream repo outside of
that org are synced into that org by the [sync job][] in Jenkins to ensure that
we can recreate a given build even if the upstream repos go away.

## Charm build specification

Charms that are to be built in Jenkaas CI must be included in the [Charm
Support Matrix][], which is a YAML list of records for each charm. Each record
must use this format:

```yaml
- charm-name:           # The key determines what the charm will be called in the store.
    tags: [""]          # List of tags used to select which charms to build.
                        # Must include "k8s" if it should be built by default.
    namespace: ""       # Namespace in the charm store to push the charm.
    upstream: ""        # Full URL to the upstream repo for the charm.
    downstream: ""      # Org and repo name portion of the GitHub URL to sync the
                        # charm to and to build from.
    build-resources: "" # Optional script to run if the charm has custom resources.
    override-build: ""  # Optional script to override how the charm is built.
    override-push: ""   # Optional script to override how the charm is pushed to the store.
```

## Build Process

The build job will automatically detect whether a charm should be built using
the legacy [charm tool][] or the newer [charmcraft][] based on whether or not
it contains a `layer.yaml` file. If a charm cannot be built directly with
either of these tools, you can use the `override-build` field to specify how
the charm should be built, but this should be avoided if possible.

## Handling Resources

The build job will also automatically handle any `oci-image` type resource
which is annotated with an `upstream-source` field. The upstream image will be
pulled and then attached to the charm when it is pushed to the store. If the
charm has other resources which must be handled differently, it will need to
specify a script in the `build-resources` field to use to build or fetch the
resources, as well as have a record in the [Resource Spec][] file.

The `build-resources` value can include the following substitutions:

  * `{src_path}` The full path to where the source repo is checked out.
  * `{out_path}` The full path where any file resources should be placed.

The Resource Spec record must use this format:

```yaml
"cs:~charm-store/url":
  resource-name: "resource-value"
  resource-name: "resource-value"
  ...
```

The record's key must be the full charm store URL for the charm, without a
revision. The resource value can either be a file path, which will also have
`{out_path}` substituted, or an image name in the local Docker cache.

Any resources not annotated with `upstream-source` or specified in the Resource
Spec record will be ignored, and the charm store will assume that whatever
resource is already attached will be carried forward. (This is generally used
for empty placeholders for optional resources, such as snaps which default to
being fetched from the snap store. These placeholder resources are manually
attached once and then never updated.)


<!-- Links -->
[build job]: https://jenkins.canonical.com/k8s/job/build-charms/
[sync job]: https://jenkins.canonical.com/k8s/job/sync-upstream/
[Charm Support Matrix]: https://github.com/charmed-kubernetes/jenkins/blob/main/jobs/includes/charm-support-matrix.inc
[charm tool]: https://snapcraft.io/charm
[charmcraft]: https://snapcraft.io/charmcraft
[Resource Spec]: https://github.com/charmed-kubernetes/jenkins/blob/main/jobs/build-charms/resource-spec.yaml
