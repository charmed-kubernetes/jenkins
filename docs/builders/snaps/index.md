# Build and Promote Snaps
Builds Kubernetes snaps from source

## Plan Phase
### Plugin: **runner**
Pull down upstream release tags and make sure our launchpad git repo has those
tags synced. Next, we push any new releases (major, minor, or patch) to the
launchpad builders for building the snaps from source and uploading to the snap
store.

#### Environment

- **SNAP_LIST**: *required*, This points to a yaml file containing the list of snaps we support. There is a list within this spec's directory: *k8s-snap-list.yaml* that can be referenced.
- **SNAP_PATCHES_LIST**: *optional*, This points to a yaml file containing the list patches to be applied prior to buiding the snap.
- **GIT_SSH_COMMAND**: *required*, Must point to a valid SSH key that will allow commits to the launchpad repos. The format for this can be `export GIT_SSH_COMMAND=\"ssh -i $HOME/.ssh/id_rsa -oStrictHostKeyChecking=no\"`
- **K8STEAMCI_USR**: *required*, Launchpad user name that has access to the snap recipes for the kubernetes build.
- **K8STEAMCI_PSW**: *required*, Launchpad password for user to access launchpad snap recipes.

**Note**: Check LP for any credentials needed.

#### Running

Set up the environment variables before running the spec:

```
export GIT_SSH_COMMAND="ssh -i $HOME/.ssh/cdkbot_rsa -oStrictHostKeyChecking=no"
export SNAP_LIST="$SNAP_LIST"
export K8STEAMCI_USR="$K8STEAMCI_USR"
export K8STEAMCI_PSW="$K8STEAMCI_PSW"
```

Next, execute the spec:

```
ogc --spec jobs/build-snaps/spec.yml --debug execute -t sync
```

### Plugin: **runner**
Handles building/promoting to the charmstore with one difference. This
job allows patches to be injected into the Kubernetes upstream code.
This is useful if a CVE is out and we need to do quick fixes without
waiting for the next patch/minor release.

#### Patches

In addition to building the snaps, this provides the ability to patch the core
Kubernetes code. The format is as follows:

Each top level key references the Kubernetes version to patch, except for `all`
as this applies to all releases.

```yaml
all:
  - master-001.patch
  - master-002.patch
1.13:
  - builders/snaps/patches/release-1.13-001.patch
1.14:
  - builders/snaps/patches/release-1.14-001.patch
1.15:
  - builders/snaps/patches/release-1.15-001.patch
```

Then in the _cmd_ section, pass the path to the above yaml file:

```yaml
plan:
  - runner:
      cmd: sync-upstream --snap-list $SNAP_LIST --force --patches jobs/build-snaps/patches.yaml
```

### Plugin: **runner**
Provides a way to promote snaps from a certain version/channel/track

