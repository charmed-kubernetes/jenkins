# Creating a stable release
This document outlines the process for publishing a Charmed Kubernetes stable release.

## Background

### Repository layout

All charm repositories used by Charmed Kuberentes have a common branch scheme to provide a
consistent experience across all code bases. Any external or shared repositories are forked
into the `charmed-kubernetes` github organization and have the following branches:

* `main`: The primary development branch. Merges are made against this branch as they are
  approved.
* `release_1.xx`: The release branch. Major releases have `main` directly merged to
  `release_1.xx`. Bugfix releases have specific commits cherry-picked to `release_1.xx`.

Tags are used to mark releases on the `release_1.xx` branch.

### Feature Freeze

2 weeks prior to a stable release the team goes into a feature freeze. At this
time only bugfixes and concentration on resolving any other outstanding issues
will take place for the first week of this freeze.

The remaining tasks will still be completed at the time of feature freeze giving
Solutions QA a solid base to test from.

### Conflict resolution

At the time of the feature freeze, new `release_1.xx` branches are created to match
our default repo branches per the documentation below. During the feature freeze and
Solutions QA period, fixes which need to be applied to address CI or QA failures
(and only those specific fixes) are cherry-picked to the respective release branches.

## Prepare CI

### $stable++ release

It may feel early, but part of releasing the next stable version requires
preparing for the release that will follow. This requires opening tracks and
building relevant snaps and charms that will be used in the new `edge` channel.

For example, we requested 1.28 snap tracks while preparing for the 1.27 release:

- https://forum.snapcraft.io/t/kubernetes-1-28-snap-tracks/34655

Bundle/charm track requests are made by emailing
`snap-store-admins@lists.canonical.com` (cc: k8s-crew)
and asking for new tracks to be opened for every neccessary
[charm](https://github.com/charmed-kubernetes/jenkins/blob/main/jobs/includes/charm-support-matrix.inc)
and
[bundle](https://github.com/charmed-kubernetes/jenkins/blob/main/jobs/includes/charm-bundles-list.inc)
owned by `Canonical Kubernetes`. For example:

- https://lists.canonical.com/mailman3/hyperkitty/list/k8s-crew@lists.canonical.com/thread/IX2VTCQRT3MLIJN2RNJZAJK2Z3KHCYXV/

### $stable release

Once upstream has an RC for the upcoming release, our CI should stop
building pre-prelease snaps. This ensures the 1.xx track will end up
with 1.xx.0 instead of 1.xx.1-alpha.0. For example, we merged the following
between 1.27 RC and GA:

- https://github.com/charmed-kubernetes/jenkins/pull/1264

Additionally, if not done already, CI should include 1.xx in the version matrix
and config for relevant jobs. For example, see these updates where we adjusted
tests for our 1.27 release:

- https://github.com/charmed-kubernetes/jenkins/pull/1139
- https://github.com/charmed-kubernetes/jenkins/pull/1270

## Preparing the release

### Create release branches for all repos

**Job**: https://jenkins.canonical.com/k8s/job/cut-stable-release/

We need to create `release_1.xx` branches from `main` for all
Charmed Kubernetes repositories. This will be our snapshot
from which we test, fix, and subsequently promote to the new release.

> **BUG:2016189**: This job is tightly coupled to the order of our
SNAP_K8S_TRACK_LIST. The last key in the list is used in the`release_1.xx`
name.

### Pin snap channel for charms in the release branches

We need to make sure that the `kubernetes-<control-plane|e2e|worker>` charms
have `1.xx/stable` set as the default snap channel. This should be done on each of
the relevant git `release_1.xx` branches. For example, for the 1.27 GA:

- https://github.com/charmed-kubernetes/charm-kubernetes-e2e/pull/28
- https://github.com/charmed-kubernetes/charm-kubernetes-control-plane/pull/283
- https://github.com/charmed-kubernetes/charm-kubernetes-worker/pull/141

> **Note**: Changes to the above repos are required as some of our customers
do not use our bundles for deployment.

### Build new CK Charms from release git branches

**Job**: https://jenkins.canonical.com/k8s/job/build-charms/

This job clones the `release_1.xx` branch for each of our repos. It then builds
each charm/bundle using those local repos. After building, they will be
published to the `1.xx/beta` channel in Charmhub based on the job options.

#### Charm build options

![charm build options](build-charms-options.png)

### Promote new K8s snaps

**Job**: https://jenkins.canonical.com/k8s/job/build-snap-from-branch/

K8s snap promotion is handled by the `sync-snaps` job and will happen
automatically after following the `Prepare CI` section above. If for some
reason you need to manually build K8s snaps from a specific branch, use the
above job with a `branch` parameter like `1.27.0`.

The `branch` parameter gets translated to `v$branch` by
[snap.py](https://github.com/charmed-kubernetes/jenkins/blob/0b334c52b2c4f816b03ff866c44301724b8b471c/cilib/service/snap.py#L172)
which must correspond to a valid tag in our
[internal k8s mirror](https://git.launchpad.net/k8s-internal-mirror/refs/).

> **Note**: Currently, the **CDK-ADDONS** snap needs to be manually built for
> the appropriate channels:
> - https://jenkins.canonical.com/k8s/job/build-release-cdk-addons-1.27/

### Run **validate-charm-release-upgrade** job

**Job**: https://jenkins.canonical.com/k8s/job/validate-charm-release-upgrade/

This validates the deployment using charms from the `latest/stable` channel,
then performing an upgrade to `latest/beta`. The tests are parameterized to
run on multiple series and with multiple snap channels.

Before running this job, confirm that the defined variables in the job are:

* `snap_version` - this release beta snap (e.g. 1.27/beta)
* `deploy_snap` - n-1 and n-2 stable snaps (e.g. 1.26/stable, 1.25/stable)

### Notify Solutions QA

At the end of the first week and assuming all major blockers are resolved, the
release is passed over to Solutions QA (SQA) for sign-off. This is done by
[publishing a CI release](https://github.com/charmed-kubernetes/jenkins/releases/new)
with a new `1.xx` tag and informing SQA of that tag. They will then have the
remaining week to test and file bugs so engineering can work towards getting
them resolved prior to GA.

Please note the [Conflict Resolution Section](#conflict-resolution) for making
any changes as a result of SQA testing.

### CNCF Conformance

**Job**: https://jenkins.canonical.com/k8s/job/conformance-cncf-ck/

Confirm passing results, then create a PR against the upstream `k8s-conformance`
repo. For example, we used the following branch for CK 1.26:

- https://github.com/charmed-kubernetes/k8s-conformance/tree/1.26-ck

And opened this upstream PR:

- https://github.com/cncf/k8s-conformance/pull/2473

### Document release notes

- Bugfixes
- Enhancements
- Known Limitations/Issues

## Performing the release

### Promote charms from `1.xx/beta` to appropriate channels

**Job**: https://jenkins.canonical.com/k8s/job/promote-charms/

This job takes a tag list, `from_channel`, and `to_channel`. A tag value of
`k8s` would only promote the charms that make up core `charmed-kubernetes`.
Ensure that `k8s-operator` is added to the tag list to include kubernetes
operator charms. You typically run this job multiple times to get charms into
all of the appropriate channels, for example:

- `1.27/beta` -> `1.27/stable`
- `1.27/beta` -> `latest/beta`
- `1.27/beta` -> `latest/stable`

#### Promote charm Options

![promote charm options](promote-charms.png)

### Promote snaps from `1.xx/<risk>` to `latest/<risk>`

**Job**: https://jenkins.canonical.com/k8s/job/sync-snaps/

This job will automatically promote snaps to `latest`. The only prereqs are
that charms have been promoted and that the `K8S_STABLE_VERSION` enum is set
to this release `1.xx`. For example, for the 1.27 GA:

- https://github.com/charmed-kubernetes/jenkins/pull/1271

> **Note**: Nightly charm and bundle builds will publish to both `latest/edge`
and `K8S_STABLE_VERSION/edge` channels.

### Pin snap channel for bundles in the release branches

We need to make sure that the bundle fragments have `1.xx/stable` set as the
default snap channel on the `release_1.xx` branch. For example, for the 1.27 GA:

- https://github.com/charmed-kubernetes/bundle/pull/879

> **Note**: Dont miss our [badges](https://github.com/charmed-kubernetes/bundle/pull/868)
like we've done so many times before!

### Build bundles to **stable**

**Job**: https://jenkins.canonical.com/k8s/job/build-charms/

Bundles cannot be promoted because they reference specific channels at build
time. Therefore, it's required to build bundles which reference the stable
charm channels.

> **Note**: The `bundle` filter shown below ensures only bundles are built
when this job runs.

#### Build bundle Options

![build bundle options](build-bundle-options.png)

### Tag release branches with the current stable bundle

**Job**: https://jenkins.canonical.com/k8s/job/sync-stable-tag-bundle-rev/

For all charm repos that make up CK, tag the existing release branches with
the most recently released stable `charmed-kubernetes` bundle revision. Use
the `1.xx/stable` version number from
[charmhub.io/charmed-kubernetes](https://charmhub.io/charmed-kubernetes),
not the `latest/stable` version number.

#### Sync Stable Tag Bundle Rev Options

![sync stable tag bundle rev options](sync-stable-tag-bundle-rev-options.png)

### Send announcement

Email announcement to k8s-crew with any relevant information.

## Post Release

When $stable++ tracks are open, add them to our CI enumerations as well as our
custom snap jobs. For example, see the additions made during our 1.27 GA to
support the future 1.28 release:

- https://github.com/charmed-kubernetes/jenkins/pull/1271

### Set cdk-addons envars

Update cdk-addons `release-1.xx` Makefile:

- https://github.com/charmed-kubernetes/cdk-addons/commit/55d42859ede457345f899b7e88ea9db904028bf3

Update cdk-addons `main` Makefile
- https://github.com/charmed-kubernetes/cdk-addons/commit/ee169e9d742f31e525c6209df8460194c2aea38d

### Bump snap channel to the $stable++ release

Bump the `kubernetes-<control-plane|e2e|worker>` charms and bundle
fragments in the `main` git branches to the future $stable++ release,
e.g. `1.28/edge`. You don't have to do this right away; in fact, you
should wait until you actually have snaps in the `$stable++/edge` channels
before making this change.

### Adjust LP milestones

Run the `[close|open]-milestone.py` scripts found in the
[cdk-scripts repo](https://github.com/canonical/cdk-scripts) repository.
For example:
```
./close-milestone.py 1.27
./open-milestone.py 1.27+ck1
```

# Fin
