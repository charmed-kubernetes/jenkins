# Charmed Kubernetes Jenkins

This project contains the scripts used to build and test Charmed Kubernetes.

## What is where

 - *jobs* - All jenkins jobs housed here
 - *jobs/integration* - All integration tests housed here

## How to run tests locally

Running the tests locally can be accomplished easily with tox. The tests expect
certain environment variables to be set. These can be found by looking at the
help output from `pytest` under the **custom options** section.

> **Note**: Required minimum Python version is 3.8.

```
> tox -e py --workdir .tox -- pytest jobs/integration/validation.py --help

custom options:
  --no-flaky-report     Suppress the report at the end of the run detailing
                        flaky test results.
  --no-success-flaky-report
                        Suppress reporting flaky test successesin the report
                        at the end of the run detailing flaky test results.
  --controller=CONTROLLER
                        Juju controller to use
  --model=MODEL         Juju model to use
  --series=SERIES       Base series
  --cloud=CLOUD         Juju cloud to use
  --charm-channel=CHARM_CHANNEL
                        Charm channel to use
  --bundle-channel=BUNDLE_CHANNEL
                        Bundle channel to use
  --snap-channel=SNAP_CHANNEL
                        Snap channel to use eg 1.16/edge
  --is-upgrade          This test should be run with snap and charm upgrades
  --upgrade-snap-channel=UPGRADE_SNAP_CHANNEL
                        Snap channel to use eg 1.16/edge
  --upgrade-charm-channel=UPGRADE_CHARM_CHANNEL
                        Charm channel to use (stable, candidate, beta, edge)
  --snapd-upgrade       run tests with upgraded snapd
  --snapd-channel=SNAPD_CHANNEL
                        Snap channel to install snapcore from
  --vault-unseal-command=VAULT_UNSEAL_COMMAND
                        Command to run to unseal vault after a series upgrade
```

This tells us what the commandline is to run this test and what parameters we
need to pass to it. These are passed to pytest running in tox. By default, the
working directory for tox is in /var/lib/jenkins, which probably doesn't exist
on development machines, so --workdir is used to specify a new directory to use.

```
tox --workdir .tox -e py3 -- \
    pytest jobs/integration/validation.py \
      --controller aws-us-east-1 \
      --model cdk \
      --cloud aws 2>&1 | tee ~/log.txt
```

## Developing new tests

Jenkins Job Builder is used to generate jobs for Jenkins programmatically. No
jobs are created by hand in the Jenkins UI.

Adding a new test can be done by copying an existing one and modifying for your needs:

[Spec](https://github.com/charmed-kubernetes/jenkins/blob/main/jobs/validate/spec)

[JJB Validate](https://github.com/charmed-kubernetes/jenkins/blob/main/jobs/validate.yaml)

## Updating jobs

Use `jenkins-jobs` to add/modify/remove tests from the Jenkins web ui. For a
single job, run the following:

```
tox --workdir .tox -e py3 -- \
    jenkins-jobs --conf jobs/jjb-conf.ini update jobs/ci-master.yaml:jobs/sync-oci-images.yaml
```

Update all jobs using the following syntax (optionally remove old jobs):
```
tox --workdir .tox -e py3 -- \
    jenkins-jobs --conf jobs/jjb-conf.ini update --delete-old jobs
```

## Job schedule

Most `build-*` jobs run daily, while `validate-` jobs are spread out throughout
the week. The `infra-*` jobs run 4 times a day and ensure any old packages
and deployments are cleaned up.

The `sync-internal-tags` job is used as part of our snap build process. Once a
new tag is seen upstream, launchpad builders will automatically sync our
repositories and build new snaps. This job should run at least twice a day to
make sure new snaps are built the same day that upstream makes a release.

Timing for any job can be adjusted with the `timed` parameter in the job yaml:

```
$ jenkins/jobs$ grep timed * 2>/dev/null
build-aws-iam-oci.yaml:      - timed: "@weekly"
build-charms.yaml:        - timed: "@daily"
build-snaps.yaml:        - timed: "@daily"
bundle-tester.yaml:        - timed: "@weekly"
infra.yaml:        - timed: "H */6 * * *"
infra.yaml:        - timed: "0 */6 * * *"
maintenance-microk8s-branches-builders.yaml:        - timed: "@hourly"
release-microk8s.yaml:        - timed: "@daily"
release-microk8s.yaml:        - timed: "@hourly"
release-microk8s.yaml:        - timed: "@hourly"
reports.yaml:        - timed: "@hourly"
sync-oci-images.yaml:        - timed: "@daily"
sync-upstream.yaml:        - timed: "@daily"
sync-upstream.yaml:        - timed: "@daily"
sync-upstream.yaml:        - timed: "H */12 * * *"
sync-upstream.yaml:        - timed: "@daily"
sync-upstream.yaml:        - timed: "@daily"
validate-hacluster.yaml:        - timed: "@monthly"
validate.yaml:        - timed: "@daily"
validate.yaml:        - timed: "@weekly"
validate.yaml:        - timed: "@monthly"
validate.yaml:        - timed: "@weekly"
validate.yaml:        - timed: "@weekly"
validate.yaml:        - timed: "@monthly"
validate.yaml:        - timed: "@daily"
validate.yaml:        - timed: "@weekly"
validate.yaml:        - timed: "@daily"
validate.yaml:        - timed: "0 0 */2 * *"
validate.yaml:        - timed: "@weekly"
validate.yaml:        - timed: "@weekly"
validate.yaml:        - timed: "@weekly"
validate.yaml:        - timed: "@monthly"
validate.yaml:        - timed: "@monthly"
validate.yaml:        - timed: "@weekly"
validate.yaml:        - timed: "@weekly"
```

After updating a job timer, be sure to run `jenkins-jobs` as described in the
*Updating jobs* section above.

## Documentation

### Build

To build the docs do the following:

```
> tox --workdir .tox -e py3 -- inv build-docs
```

To build and deploy documentation (requires AWS credentials):

```
> tox --workdir .tox -e docs
```


