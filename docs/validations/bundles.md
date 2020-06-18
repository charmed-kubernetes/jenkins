# Custom Bundles

Process for submitting custom bundles to be tested

## Requirements

1. A bundle file
2. If verification is required then the bundle should have a section that looks
   something like this:

```yaml
verify: |
  #!/bin/bash
  set -x

  echo "I am verifying this bundled i just deployed."
  exit 0
```

This should sit somewhere in the top-level of your bundle, Juju will disregard
any keys it doesn't know about so this will still deploy as normal.

The top-level key must be **verify** otherwise the test tool will not pick it up.

## Deploy Environment

All bundles will be deployed while in an activated python virtual environment.
So you'll have access to install any necessary python tools required to run
things such as pytest etc.

Common tools already provided:

- juju
- juju-wait
- pytest
- tox

## Open a Github PR

Open a PR at https://github.com/charmed-kubernetes/jenkins and place the custom
bundle file in `jobs/bundles/`. Please name the actual file something relevant,
for example, if you created a bundle with LMA then you could call it
`kubernetes-lma-stack.yaml`. The test tool will use the basename of that file
when doing its reporting and storage of results.

## After a PR is merged

Once merged, the test tool will run weekly, testing all bundle files in
`jobs/bundles`. If verification is done, those results will be reported and
shown in the CI dashboard.
