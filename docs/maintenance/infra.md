# CI Infrastructure
Provides support tasks for maintaining Jenkins

## Jobs

### `infra-maintain-{node}`

Runs every 6 hours on each persistent agent. One job per node:

- `jenkins-agent-amd64-large-0` through `jenkins-agent-amd64-large-6`
- `jenkins-agent-arm64-large-0`
- `jenkins-agent-s390x-large-0`

Each job self-maintains its own agent via `--limit localhost`. It:

1. Breaks any stale dpkg locks and runs `apt dist-upgrade`.
2. Runs `jobs/infra/fixtures/cleanup-local.sh` — destroys leftover Juju
   controllers and reclaims local disk (docker, lxd, venvs, tmp).
3. Runs `jobs/infra/playbook-jenkins.yml` — provisions the agent toolchain
   (apt/snap packages, LXD, Docker, proxy config) and drops credentials.

### `infra-cleanup-clouds`

Runs every 6 hours on any free `amd64 && large` agent. Purges stale cloud
resources across AWS, GCE, and Azure that were created by CI jobs. Runs once
globally rather than redundantly on every agent.

## Ansible

The playbook is located at `jobs/infra/playbook-jenkins.yml`.

Credentials are pulled from the Jenkins Credentials store via the
`ci-creds-infra` wrapper defined in `jobs/ci-master.yaml`. To run the
playbook locally, the credential environment variables listed under that
wrapper must be set.

## Cleanup scripts

- `jobs/infra/fixtures/cleanup-local.sh` — local agent cleanup (Juju
  controllers, docker, lxd, apt, tmp). Called by each maintain job.
- `jobs/infra/fixtures/cleanup-clouds.sh` — AWS/GCE/Azure account-wide
  purge. Called by `infra-cleanup-clouds` only.
