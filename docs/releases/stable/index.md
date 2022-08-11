# Creating a stable release
Outlines the processes for publishing a new Charmed Kubernetes release.

## Stable Release Process

### How to read this document

Each step in the release process contains information pertaining to the
description of the jobs and what is required if needing to run the jobs
locally.

Each step should contain the following:

- Job name as seen in jenkins
- Description
- Any additional notes/caveats
- Example jenkins screenshots if necessary on the options that should be used.

### Feature Freeze

2 weeks prior to a stable release the team goes into a feature freeze. At this
time only bugfixes and concentration on resolving any other outstanding issues
will take place for the first week of this freeze.

The remaining tasks will still be completed at the time of feature freeze giving
Solutions QA a solid base to test from.

#### Conflict resolution

At the time of the feature freeze, the stable branches are git reset to match
the default branches at that point, per the documentation below. During the
feature freeze and Solutions QA period, fixes which need to be applied to
address CI or QA failures, and only those specific fixes, are cherry-picked in
to the stable branches.

## Prepare CI

### $next release

Once upstream has an RC for the next stable release, our CI should stop
building pre-prelease snaps. This ensures the 1.xx/edge channel will end up
with 1.xx.0 instead of 1.xx.1-alpha.0.

https://github.com/charmed-kubernetes/jenkins/pull/764

Additionally, if not done already, CI should be including the 1.xx/edge in the
version matrix for relevant tests. For example, see the 1.23 update where we
add n and drop n-4 from our test matrix:

https://github.com/charmed-kubernetes/jenkins/pull/761

### $next++ release

It may feel early, but part of releasing the next stable version requires
preparing for the release that will follow. This requires opening tracks and
building relevant snaps and charms that will be used in the new 'edge' channel.

For example, we requested 1.24 tracks while preparing for the 1.23 release:

https://forum.snapcraft.io/t/kubernetes-1-24-snap-tracks/27828

We also added support for CI to build/upload to those requested tracks (k8s
snaps as well as cdk-addons):

- https://github.com/charmed-kubernetes/jenkins/pull/765/files
- https://github.com/charmed-kubernetes/jenkins/commit/b0ce1fb0053908043ce25f10cca40be6531c3156

Charm tracks can be created by contacting [~snapstore](https://chat.canonical.com/canonical/channels/snapstore) and asking for new tracks to be opened for every neccessary [charm](https://charmhub.io/charm) and [bundle](https://charmhub.io/bundle) owned by `Canonical Kubernetes` on [charmhub.io](https://charmhub.io)

## Preparing the release

### Tag existing stable branches with the current stable bundle
#### :warning: **Deprecated Step**

Starting with release 1.24, each repo has a unique branch for each 
Charm release. This step was previously necessary to tag the 
previous stable release before resyncing each branch from `main` -> `stable`.
Tagging of the `release_x.xx` branch will now take place at the end of the release.

> For all charm repos that make up CK, tag the existing stable branches with
> the most recently released stable `cs:charmed-kubernetes` bundle revision.
>
> **Job**: https://jenkins.canonical.com/k8s/job/sync-stable-tag-bundle-rev/

### Submit PR to bump K8S Track Map

Add the next release to the track map enumerations. To use the newly created tracks, 
include the next release to the track list/map.

```python
    ...
    ("1.25", ["1.25/beta", "1.25/edge"]),
]
```

Example PR:
 - https://github.com/charmed-kubernetes/jenkins/pull/974

This will allow and charm-builds targetting `edge` or `beta` channels to flow to the
`1.25` tracks while any charm-builds targetting `candidate` or `stable` will flow to
`1.24` tracks.

:warning: Nightly charm and bundle builds will target `latest/edge` and this `{track}/edge`

### Reset release_x.xx from `default` git branches

Once all repositories are tagged, we need to create release branches from
`main`. This will be our snapshot from which we test, fix, and subsequently
promote to the new release.

**Job**: https://jenkins.canonical.com/k8s/job/cut-stable-release/

### Submit PR's to bundle and charms to pin snap channel on the release branches

We need to make sure that the bundle fragments and kubernetes-worker/control-plane/e2e
are set to `<k8sver>/stable`. This should be done on each of the relevant git
`stable` branches. For example, for 1.23 GA:

- https://github.com/charmed-kubernetes/bundle/pull/815
- https://github.com/charmed-kubernetes/charm-kubernetes-e2e/pull/15
- https://github.com/charmed-kubernetes/charm-kubernetes-master/pull/192
- https://github.com/charmed-kubernetes/charm-kubernetes-worker/pull/104

> Note: The charms themselves also need to be done as some do not use our
  bundles for deployment.

### Bump snap channel to next minor release

Once the rebase has occurred we need to bump the same charms and bundle
fragments in the `main` git branches to the next k8s minor version,
e.g. `1.24/edge`. You don't have to do this right away; in fact, you
should wait until you actually have snaps in the `$next/edge` tracks
before making this change.

### Build new CK Charms from release git branches

**Job**: https://jenkins.canonical.com/k8s/job/build-charms/

Pull down all layers and checkout their release branches. From there build
each charm against those local branches. After the charms are built they need to be
promoted to the **beta** channel in the charmstore.

> **Note**: Beta channel is required as any bugfix releases happening at the
  same time will use the candidate channels for staging those releases.

#### Charm build options

![charm build options](build-charms-options.png)

### Promote new K8s snaps

K8s snap promotion to `beta` is handled by the `sync-snaps` job and will happen
automatically after following the `Prepare CI` section noted above. If for some
reason you need to manually build K8s snaps from a specific branch, use the
following job with a `branch` parameter like `1.23.0`:

**Job**: https://jenkins.canonical.com/k8s/job/build-snap-from-branch/

The `branch` parameter gets translated to `v$branch` by
[snap.py](https://github.com/charmed-kubernetes/jenkins/blob/0b334c52b2c4f816b03ff866c44301724b8b471c/cilib/service/snap.py#L172)
which must correspond to a valid tag in our
[internal k8s mirror](https://git.launchpad.net/k8s-internal-mirror/refs/).

> **Info**: Please note that currently **CDK-ADDONS** snap needs to be
    manually released to the appropriate channels:
    **Job**: https://jenkins.canonical.com/k8s/job/build-release-cdk-addons-amd64-1.23/

### Notify Solutions QA

At the end of the first week and assuming all major blockers are resolved, the
release is passed over to Solutions QA (SolQA) for a final sign-off. This is done
by tagging the current Jenkins commit with the release version and informing SolQA
of that taga. SolQA will then have the remaining week to test and file bugs as they
happened so engineering can work towards getting them resolved prior to going GA.

Please note the [Conflict Resolution Section](#conflict-resolution) for making
any changes as a result of their testing.

### CNCF Conformance

**Job**: https://jenkins.canonical.com/k8s/job/conformance/

### Document release notes

- Bugfixes
- Enhancements
- Known Limitations/Issues

## Performing the release

### Promote charms from **beta** to **stable**

This job takes a tag, from_channel, and to_channel. The tag defaults to `k8s` so
it will only promote the necessary charms that make up charmed-kubernetes (the
others are kubeflow related).

**Job**: https://jenkins.canonical.com/k8s/job/promote-charms/

#### Promote charm Options

![promote charm options](promote-charms.png)

**Job**: https://jenkins.canonical.com/k8s/job/promote-bundles/


### Submit PR to bump K8S Track Map

Add candidate and stable branches to the track map

```diff
-     "1.25": ["1.25/beta", "1.25/edge"],
+     "1.25": ["1.25/stable", "1.25/candidate", "1.25/beta", "1.25/edge"],
}
```

This will allow and charm-builds targetting all channels to flow to the
`1.25` tracks.

### Build bundles to **stable**

Bundles cannot be promoted because when built they reference specific charm channels
Therefore, it's required to build bundles which reference the stable charm channels. 

#### Build bundle Options

![build bundle options](build-bundle-options.png)

### Tag release branches with the current stable bundle

For all charm repos that make up CK, tag the existing release branches with
the most recently released stable `charmed-kubernetes` bundle revision.

Use the `x.xx/stable` version number from [charmhub.io/charmed-kubernetes](https://charmhub.io/charmed-kubernetes), not the `latest/stable` version number

> **Job**: https://jenkins.canonical.com/k8s/job/sync-stable-tag-bundle-rev/

#### Sync Stable Tag Bundle Rev Options

![sync stable tag bundle rev options](sync-stable-tag-bundle-rev-options.png)

### Promote snaps from <stable track>/stable to latest/<risks>

This promotion is handled by the `sync-snaps` job. Once charms and bundles
have been promoted, set the `K8S_STABLE` enum to the release semver. For
example, for 1.22 GA:

https://github.com/charmed-kubernetes/jenkins/pull/728

### Send announcement

Email announcement to k8s-crew with any relevant information.

