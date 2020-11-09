# Patching Snap and Debian packages

## Repo locations

- https://launchpad.net/k8s-internal-mirror
- https://launchpad.net/cri-tools
- https://launchpad.net/kubernetes-cni-internal

## Creating a patch

Depending on what's being patched, for example, Kubernetes will need to contain
a branch that can be automatically picked up by our build service. Patches can
only be applied to the latest MAJOR.MINOR.PATCH revision in the series. What
this means is that if Kubernetes is at release **1.19.3** then only patched
versions of that release will be noticed and processed.

The format for creating a patch is as follows:

```
MAJOR.MINOR.PATCH+patch.X
```

In this case to patch a **1.19.3** release, a branch would need to be created with the following:

```
v1.19.3+patch.1
```

### Steps

For the repo you want to patch you must first clone and checkout the approriate branch:

```
git clone git+ssh://GIT_USER@git.launchpad.net/k8s-internal-mirror
git checkout v1.19.3
```

Apply any patches to this branch and then create the patched branch off of the working tree

```
git checkout v1.19.3+patch.1
```

Next commit any changes and push **v1.19.3+patch.1** up to the repository.

## Subsequent patches for existing patched branches

If subsequent patches are required for the same MAJOR.MINOR.PATCH release then
the patched version will need to be incremented building off the previous
patched released. So if you already have a branch **v1.19.3+patch.1** you would
then create a new branch based off that patched branch with the name of
**v1.19.3+patch.2**.

### Steps

Perform the steps from above in creating a patch replacing the MAJOR.MINOR.PATCH with the previous patched branch:

```
git checkout v1.19.3+patch.1
```

Apply any changes and create the next patched branch

```
git checkout v1.19.3+patch.2
```

Commit and push the newly created branch to the repository and that branch will
be used during the next automatic run of the deb/snap builder job.

## Note

Keep in mind that whatever is patched, those fixes will automatically make it in
to both Snap _and_ Debian package builds to be automatically built and
published.

If you need to kick off jobs sooner than later the jobs to run are:

- [sync-snaps](https://jenkins.canonical.com/k8s/job/sync-snaps/)
- [sync-debs](https://jenkins.canonical.com/k8s/job/sync-debs/)

## Determining what and where the patches come from

Patches will usually come from an opened LP bug that relates to one of the above
repos, those patches can be attached to the bug or a link to an upstream commit.
Since the actual patching is done by a physical person the options for getting
that patch in can be determined on the best workflow that works for the team.
