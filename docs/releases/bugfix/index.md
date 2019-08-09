# Creating a bugfix release
Performs a Kubernetes bugfix release, which includes validation across the base
deployment as well as variations including calico, tigera, vault, nvidia, and
ceph.

## Bugfix Release Process

### Cherry-pick fixes from master into stable branches

### Document release notes

- Bugfixes
- Enhancements
- Known Limitations/Issues

### Run the **release-charm-bugfix** job

**Job**: https://jenkins.canonical.com/k8s/job/release-charm-bugfix/

This is the main job to run when needing to do a bugfix. The steps this build performs are as follows:

- Build and Publish charms to the `beta` channel. You can override the channel if needed.
- The validation suite is run against a deployed `charmed-kubernetes`
- The validation suite is run against the following variations:
    - NVidia
    - Vault
    - Tigera EE
    - Calico
    - Ceph

**Note**: Keep up with the `release_id` as that will need to be referenced in
case the job needs to be re-run due to build errors. Simply hitting `Rebuild`
on the Jenkins job page will have that ID prepopulated.

### Validate a minor upgrade

**Job**: https://jenkins.canonical.com/k8s/view/Validate%20Upgrades/job/validate-minor-upgrade-v1.14.x-v1.15.x/

This will deploy the previous Charmed Kubernetes release using the stable charm
channel and allow you to upgrade to a different snap and charm channel.
Typically, in this case we set the `upgrade_snap_channel` to the latest stable
release (ie. 1.15/stable) and set the `upgrade_charm_channel` to `beta`.

### Promote charms from `beta` to `candidate` and `stable`

**Job**: https://jenkins.canonical.com/k8s/job/promote-charms/

This job takes a tag, from_channel, and to_channel. The tag defaults to `k8s` so
it will only promote the necessary charms that make up charmed-kuberneetes (the
others are kubeflow related).

### Promote bundles from `beta` to `candidate` and `stable`

**Job**: https://jenkins.canonical.com/k8s/job/promote-bundles/

Same as charm promotion.

### Send announcement to k8s-crew with any relevant information.

