# Charm build specification

Each charm that is to be built in Jenkaas CI must adhere to a specific interface
so that CI can easily build all charms in a uniformed way.

## Build Interface

The interface consists of a Makefile that responds to the following targets:

- make charm
- make upload

Additionally, for `make upload` target it accepts the following variables:

- **NAMESPACE** - This is the charmstore namespace in which the charm is to be uploaded to
- **CHANNEL** - This is the channel that the resulting charm plus any resources will be published to.

## Usage

Making the charm takes no additional input so the following should result in a
built charm suitable for upload:

```bash
$ make charm
```

In this example, the charm will be uploaded to the `containers` namespace and be
published to the `edge` channel:

```bash
$ make NAMESPACE=containers CHANNEL=edge upload
```

## Implementation

There is no set way to implement the Makefile targets, however, a good pattern
to use is have a set of scripts that reside in a `script/` directory that performs
the necessary tasks.

A good example of this can be seen with the **sriov-cni charm**[^1]. This
project uses the scripts to rule them all[^3] pattern incorporated by GitHub and
would allow each charm repo to be managed and developed on in a similar fashion.

The current pattern for developing scripts to satisfy the Makefile targets are as follows:

### script/bootstrap

This script is solely for fulfilling dependencies of the project. In our
reference repo[^1] we install the necessary snaps, deb packages, and python related
dependencies here.

This is typically a dependent target on the `make charm` target.

### script/build

This script handles the actual building of the charm. Not all charms are built
the same way as there are reactive charms and the new operator framework which
currently have different tools to build them. This script is intended to hide
those details during build.

This is typically used by the `make charm` target.

### script/upload

This script handles uploading the charm to the charmstore. In the reference
repo[^1], it also makes use of the environment variables passed via the Makefile
target to know where and what charm to upload.

This is typically used by the `make upload` target.

## CI

Adding some additional checks on making sure that the charm builds properly with
each push/pull request is also a good idea. In the reference repo[^1] there is a
**GitHub workflow**[^2] setup to accomplish that.


## References

[^1]: https://github.com/charmed-kubernetes/charm-sriov-cni
[^2]: https://github.com/charmed-kubernetes/charm-sriov-cni/blob/master/.github/workflows/build.yml
[^3]: https://github.com/github/scripts-to-rule-them-all
