# Builds snaps
Builds Kubernetes snaps from source
#### Environment

- **GIT_SSH_COMMAND**: *required*, Must point to a valid SSH key that will allow commits to the launchpad repos. The format for this can be `export GIT_SSH_COMMAND=\"ssh -i $HOME/.ssh/id_rsa -oStrictHostKeyChecking=no\"`
- **K8STEAMCI_USR**: *required*, Launchpad user name that has access to the snap recipes for the kubernetes build.
- **K8STEAMCI_PSW**: *required*, Launchpad password for user to access launchpad snap recipes.

**Note**: Check LP for any credentials needed.

#### Running

```
export GIT_SSH_COMMAND=\"ssh -i $HOME/.ssh/cdkbot_rsa -oStrictHostKeyChecking=no\"
export K8STEAMCI_USR=\"$K8STEAMCI_USR\"
export K8STEAMCI_PSW=\"$K8STEAMCI_PSW\"

tox -e py38 -- python jobs/sync-upstream/sync.py snaps
```

<!-- Links -->
[Snap Support List]: https://github.com/charmed-kubernetes/jenkins/blob/main/jobs/includes/k8s-snap-list.inc
