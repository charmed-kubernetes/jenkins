# CI Infrastructure
Provides support tasks for maintaining Jenkins

## Jobs

### `infra-maintain-{node}`

Runs every 6 hours on each persistent agent. One job per node:

- `jenkins-kubernetes-ps7-amd64-large-agents-jenkins-agent-amd64-large-7`
  through `...-13` (amd64)
- `jenkins-kubernetes-ps7-arm64-large-agents-jenkins-agent-arm64-large-0` (arm64)
- `jenkins-kubernetes-ps7-s390x-large-agents-jenkins-agent-s390x-large-0` (s390x)

Each job self-maintains its own agent via `--limit localhost`. It:

1. Breaks any stale dpkg locks and runs `apt dist-upgrade`.
2. Runs `jobs/infra/fixtures/cleanup-local.sh` — destroys leftover Juju
   controllers and reclaims local disk (docker, lxd, venvs, tmp).
3. Runs `jobs/infra/playbook-jenkins.yml` — provisions the agent toolchain
   (apt/snap packages, LXD, Docker, proxy config) and drops credentials.

### `infra-cleanup-clouds`

Runs every 6 hours on any free `amd64 && large` agent. Purges stale cloud
resources across AWS and GCE that were created by CI jobs. Runs once
globally rather than redundantly on every agent. Fails if the agent lacks
`aws`, `jq`, `parallel`, or `gcloud` (provisioned by the playbook), or if
either cloud rejects its credentials (AWS reads the bound `AWSCREDS` file). Azure
purge is shelved until an Azure job runs on PS7; see the `NOTE:` in
`jobs/infra/fixtures/cleanup-clouds.sh`.

## Ansible

The playbook is located at `jobs/infra/playbook-jenkins.yml`.

Credentials are pulled from the Jenkins Credentials store via the
`ci-creds-infra` wrapper defined in `jobs/ci-master.yaml`. To run the
playbook locally, the credential environment variables listed under that
wrapper must be set.

## Cleanup scripts

- `jobs/infra/fixtures/cleanup-local.sh` — local agent cleanup (Juju
  controllers, docker, lxd, apt, tmp). Called by each maintain job.
- `jobs/infra/fixtures/cleanup-clouds.sh` — AWS/GCE account-wide purge
  (Azure shelved). Called by `infra-cleanup-clouds` only.
