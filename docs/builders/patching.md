# Patching Snap and Debian packages

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

If subsequent patches are required for the same MAJOR.MINOR.PATCH release then
the patched version will need to be incremented building off the previous
patched released. So if you already have a branch **v1.19.3+patch.1** you would
then create a new branch based off that patched branch with the name of
**v1.19.3+patch.2**. This will ensure that the automated builder will pick up
the latest patched revision and build those packages instead.

We have private repos that we maintain for all the components we support.
Branches must be created off those private repos in order to be processed by our
builders.

Keep in mind that whatever is patched, those fixes will automatically make it in
to both Snap _and_ Debian package builds to be automatically built and
published.
