# Creating a bugfix release
This document outlines the process for publishing a Charmed Kubernetes bugfix release.

## Background

### Repository layout

All charm repositories used by Charmed Kuberentes have a common branch scheme to provide a
consistent experience across all code bases. Any external or shared repositories are forked
into the `charmed-kubernetes` github organization and have the following branches:

* `main`: The primary development branch. Merges are made against this branch as they are
  approved.
* `release_x.xx`: The release branch. Major releases have `main` directly merged to
  `release_x.xx`. Bugfix releases have specific commits cherry-picked to `release_x.xx`.

Tags are used to mark releases on the `release_x.xx` branch.

### Preparing the release milestone

All Charmed Kubernetes charms, interfaces, and layers are revisioned together via
[milestones][milestones]. To complete a bugfix release, all bugs listed for the
milestone will need to have their pull requests cherry-picked onto the appropriate
release branch.

#### Reconcile bugs

Determine which bugs will be included in this release and set their launchpad
milestone accordingly.

#### Setup the next milestone

Any milestone bugs that will not make it into this release should be moved to either
the next major (e.g. 1.26) or the next bugfix (e.g. 1.25+ck2) milestone.

If the next milestone does not exist, create it with the `create-milestone.py` script
found in the [cdk-scripts repo][cdk-scripts]. This will create a new milestone for
every launchpad project in the Charmed Kubernetes group. For example:
```
./create-milestone.py 1.25+ck2
```

### Performing the cherry-pick

For each milestone bug, review the comments and cherry-pick all pull requests onto the
appropriate `release_x.xx` branch. Some bugs will require doing this for multiple repos,
so be sure to get all pull requests listed in the bug.

After you complete all cherry-picks for a given bug, remove the "backport-needed" tag.
You can push to `release_x.xx` as you complete each cherry-pick; the release won't
happen automatically even if you do not complete this process in a single sitting.

If there are trivial merge conflicts, fix them and continue. If there are non-trivial
merge conflicts, create a PR and ask another team member to review.

When all bugs in the milestone are done, you are ready to proceed.

### Document release notes

Create a PR against the [docs repo][docs-repo] with release notes including:

* Bugfixes
* Enhancements
* Known Limitations/Issues

### Tag release branches with bugfix revision

**Job**: https://jenkins.canonical.com/k8s-ps5/job/sync-stable-tag-bugfix-rev/

This will tag all `release_x.xx` branches with the k8s version and bugfix revision.
For example, the first bugfix release for 1.25 will tag the `release_1.25` branch
with **1.25+ck1**.

#### Charm tag options

![bugfix tag options](bugfix-tag-options.png)

### Run the **build-charms** job

**Job**: https://jenkins.canonical.com/k8s-ps5/build-charms/

This will build charms from the `release_x.xx` branch and promote them to the
x.xx/candidate channel for testing.

#### Charm build options

![build charm options](bugfix-options.png)

### Verify Commit SHAs of charms/layers/interfaces

> NOTE: (kwm) i do not think we do this anymore since the migration to charmhub.

Verify the charm manifests for the build charms matches the commit SHAs of
the stable branches of what was built in the previous build-charms job:

https://github.com/Cynerva/cdk-release-checkers

### Build cdk-addons

Run build jobs for n, n-1, and n-2 versions of cdk-addons. For example, if
doing a 1.25+ckX release, run:

* build-release-cdk-addons-amd64-1.25
* build-release-cdk-addons-amd64-1.24
* build-release-cdk-addons-amd64-1.23

### Required Testing

#### Confirm that todays builds are in the "latest/candidate" channel of charmhub

```bash
charms=(list of charm names)
for charm in ${charms[@]}; do
echo $charm - $(juju info $charm --channel=candidate | grep candidate)
done
```

#### Run **validate-charm-bugfix**

**Job**: https://jenkins.canonical.com/k8s-ps5/validate-charm-bugfix/

This validates the deployment using the charms from the candidate channel.

#### Run **validate-charm-bugfix-upgrade**

**Job**: https://jenkins.canonical.com/k8s-ps5/validate-charm-bugfix-upgrade/

This deploys `charmed-kubernetes` from the stable channel, upgrades the charms to
the candidate channel, then validates the deployment.

#### Examine results

**Results**: http://jenkaas.s3-website-us-east-1.amazonaws.com/

Verify that the `validate-charm-bugfix-*` tests are passing. If failures occur:

* fix the broken test or charm in `main`
* cherry-pick charm fixes to the `release_x.xx` branch
* re-tag, re-build, and re-test per the above steps

### Promote charms from candidate to stable

**Job**: https://jenkins.canonical.com/k8s-ps5/promote-charms/

This job takes a tag, from_channel, and to_channel. The tag defaults to
`k8s,k8s-operator` to promote all charms that make up Charmed Kubernetes.

**Note about `to_channel`**

If this is a bugfix for the current latest/stable release:

`ex) 1.25 is the current release, and this is a bugfix for 1.25`
* set the `from_channel` = `candidate`
* set the `to_channel` = `stable`
* the charms will be released to both `latest/stable` and `1.25/stable`

If this is a bugfix for a previous major release:

`ex) 1.25 is the current release, but this is a bugfix for 1.24`
* set the `from_channel` = `1.24/candidate`
* set the `to_channel` = `1.24/stable`
* the charms will be released to only `1.24/stable`

### Build stable bundles

**Job**: https://jenkins.canonical.com/k8s-ps5/build-charms/

Bundles should not be promoted because a candidate bundle points to candidate charms.
Instead, rebuild the bundles targetting the correct `to_channel`. It's possible this
does not result in a new bundle if the `bundle.yaml` hasn't changed since the
previous release.

**Note about `to_channel`**

If this is a bugfix for the current latest/stable release:

`ex) 1.25 is the latest release, and this is a bugfix for 1.25`
* set the `to_channel` = `stable`
* the bundles will be released to both `latest/stable` and `1.25/stable`

If this is a bugfix for a previous major release:

`ex) 1.25 is the latest release, but this is a bugfix for 1.24`
* set the `to_channel` = `1.24/stable`
* the bundles will be released to only `1.24/stable`

Run the job for the `charmed-kubernetes` bundle with the following:
  * layer_branch = release_x.xx
  * charm_branch = release_x.xx
  * bundle_branch = release_x.xx
  * to_channel = `see-note-above`
  * filter_by_tag = charmed-kubernetes

Run the job again for the `kubernetes-core` bundle:
  * layer_branch = release_x.xx
  * charm_branch = release_x.xx
  * bundle_branch = release_x.xx
  * to_channel = `see-note-above`
  * filter_by_tag = kubernetes-core

### Promote cdk-addons

Promote **cdk-addons** snaps from candidate to stable for n, n-1, and n-2
tracks. For example, if doing a 1.25+ckX release, then you would promote:

* 1.25/candidate -> 1.25/stable
* 1.24/candidate -> 1.24/stable
* 1.23/candidate -> 1.23/stable

This could be done using the following one-liner:
```
for track in 1.23 1.24 1.25; do for rev in `snapcraft revisions cdk-addons | grep "$track/candidate\*" | cut -d ' ' -f 1`; do snapcraft release cdk-addons "$rev" "$track/stable"; done; done
```

Also promote the n/candidate revision to latest/stable, for example:
```
for rev in `snapcraft revisions cdk-addons | grep "1.25/candidate\*" | cut -d ' ' -f 1`; do snapcraft release cdk-addons "$rev" "latest/stable"; done;
```

### Close the milestone

Run the `close-milestone.py` script found in the [cdk-scripts repo][cdk-scripts].
For example:
```
./close-milestone.py 1.25+ck1
```

### Send announcement to k8s-crew with any relevant information

[cdk-scripts]: https://github.com/canonical/cdk-scripts
[docs-repo]: https://github.com/charmed-kubernetes/kubernetes-docs
[milestones]: https://launchpad.net/charmed-kubernetes/+milestones
