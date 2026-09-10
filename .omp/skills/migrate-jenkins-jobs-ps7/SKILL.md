---
name: migrate-jenkins-jobs-ps7
description: "Migrate charmed-kubernetes/jenkins jobs from the legacy PS5 Jenkins to the PS7 controller — node labels, egress proxy, root agents, snapcraft store creds, LXD/noble bases, and freestyle→Declarative Pipeline conversion. Use when porting any jobs/*.yaml, *.groovy, or Jenkinsfile that still targets runner-* labels."
---

# Migrating CI jobs to PS7

The `ps7/main` branch already migrated `build-charms`, `promote-charms`,
`promote-bundles`, `build-release-cdk-addons`, `build-release-eks-snaps`, and the
whole `infra` job family. **Copy those patterns; do not invent new ones.**

Reference commits (`git log main..ps7/main`):

| Commit | What it teaches |
|---|---|
| `1afe2c36` | infra job family: per-node maintain jobs, `ci-creds-infra`, split cleanup scripts |
| `dc2daedf` | plugin/snapcraft-login removal, proxy in `cilib.sh`, noble bases, secret-interpolation fix |
| `31ce749d` | how to shelve a stage that cannot run on PS7 (comment it out + `NOTE:` explaining the follow-up) |
| `b9fe3ee6` | Groovy `"""` interpolation vs shell expansion |
| `f037e2c0`, `5ba4b6ee` | freestyle → Declarative Pipeline conversion (canonical exemplar) |
| `77743c12` | plugins missing on PS7: no `ansiColor`/`timestamps` in pipeline `options {}` |

Canonical exemplars to read before editing anything:

- `jobs/build-charms/build-charms.groovy` — full pipeline w/ LXD, tox, cleanup `post`
- `jobs/build-charms/promote-charms.groovy` — minimal pipeline
- `jobs/build-charms.yaml` — the JJB side of a pipeline job
- `jobs/infra.yaml` — a freestyle job that stayed freestyle

## PS7 environment invariants

| Concern | PS5 (old) | PS7 (new) |
|---|---|---|
| Agent labels | `runner-amd64`, `runner-cloud`, `runner-validate`, `runner-ps5-*` | `amd64 && large`, `arm64 && large`, `s390x && large` |
| Named agents | `runner-{arch}` | `jenkins-kubernetes-ps7-{arch}-large-agents-jenkins-agent-{arch}-large-N` |
| Agent user | `jenkins` | **`root`** — no `jenkins` user, no `docker`/`lxd` group juggling |
| Egress | transparent + `squid.internal:3128` | **no transparent egress**; everything through `http://egress.ps7.internal:3128` |
| Base image | `ubuntu:20.04` | `ubuntu:24.04` (noble) |
| Python | `python3.8` (`run-tox` builder) | system `python3` + `venv` + `tox -e py` |
| Snapcraft auth | `snapcraft login --with <file>` | `SNAPCRAFT_STORE_CREDENTIALS=$(< <file>)` |
| MTU workarounds | docker `mtu: 1458`, `lxc network set bridge.mtu 1458` | removed — default MTU works |
| Plugins | ansicolor, timestamps available in pipelines | **not available**; `default-job-wrapper` still works for freestyle |
| SCM branch | `main` | `ps7/main` (see `k8s-jenkins-jenkaas` in `jobs/ci-master.yaml`) |

## Decide: convert to pipeline, or keep freestyle?

Convert to a Declarative Pipeline when the job body is a `run-tox`/`run-venv`
shell blob with multiple logical phases, LXD container lifecycle, or needs
per-stage failure attribution. That is what `build-charms`, `promote-charms`,
and `promote-bundles` got.

Keep freestyle when the job is a short shell script with no container lifecycle
(`infra-maintain-{node}`, `infra-cleanup-clouds`). Freestyle jobs keep
`default-job-wrapper` and the `set-env` builder.

Jobs that are *already* pipelines (`build-release-*`, `sync-oci-images`,
`build-ck-docs`, `aws-iam-docker`, `validate-hacluster`) only need the
environment/label/proxy/snapcraft transforms — do not restructure them.

## Transform checklist

Work one job file at a time. Apply every item that fits.

### 1. Node labels

```yaml
# before
node: runner-amd64          # or runner-cloud, runner-validate
# after
node: 'amd64 && large'
```

Parameterised builders: `default: 'runner-{arch}'` → `default: '{arch} && large'`.
`runner-cloud` and `runner-validate` have no PS7 equivalent — they become
`amd64 && large` unless the job genuinely needs another arch.

Anything that must pin a *specific* machine (infra maintenance) uses the full
agent name and a `{node}` job-template axis; see `jobs/infra.yaml`.

### 2. Freestyle → Declarative Pipeline (JJB side)

```yaml
# before
    node: runner-cloud
    project-type: freestyle
    scm:
      - k8s-jenkins-jenkaas
    ...
    wrappers:
      - default-job-wrapper
      - ci-creds
    builders:
      - set-env: {JOB_SPEC_DIR: "jobs/foo"}
      - run-tox: {COMMAND: "..."}

# after
    project-type: pipeline
    pipeline-scm:
      scm:
        - k8s-jenkins-jenkaas
      script-path: jobs/foo/foo.groovy
```

The `node`, `wrappers`, and `builders` keys are **deleted** — the pipeline
declares its own agent, credentials, and steps. `parameters`, `properties`,
`triggers`, and `description` stay in the YAML.

### 3. Pipeline `environment` block

`set-env` does not exist in pipelines; restate it. Baseline (copy verbatim,
trim what the job does not use):

```groovy
    environment {
        HOME                 = "/var/lib/jenkins"
        PATH                 = "/snap/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
        LC_ALL               = "C.UTF-8"
        LANG                 = "C.UTF-8"
        HTTP_PROXY           = "http://egress.ps7.internal:3128"
        HTTPS_PROXY          = "http://egress.ps7.internal:3128"
        http_proxy           = "http://egress.ps7.internal:3128"
        https_proxy          = "http://egress.ps7.internal:3128"
        NO_PROXY             = "localhost,127.0.0.1"
        no_proxy             = "localhost,127.0.0.1"
        PYTHONPATH           = "$WORKSPACE"
        TMPDIR               = "/tmp/$BUILD_TAG"
    }
```

Both upper- and lower-case proxy vars are required: curl/git honour lowercase,
python/requests honour uppercase.

Charm jobs additionally need the `CHARM_*` tree — copy the block from
`jobs/build-charms/promote-charms.groovy`. Where the YAML exposes
`CHARM_BUILD_DIR`/`CHARM_LAYERS_DIR`/`CHARM_INTERFACES_DIR` as parameters, use the
`params.X?.trim() ? params.X : 'default'` form from `build-charms.groovy`.

### 4. Credentials

The `ci-creds` wrapper is freestyle-only. In a pipeline, bind exactly the
credentials the job uses:

```groovy
        CHARMCRAFT_AUTH = credentials('charmcraft_creds')
        LPCREDS         = credentials('launchpad_creds')
        CDKBOT_GH       = credentials('cdkbot_github')   // -> CDKBOT_GH_USR / CDKBOT_GH_PSW
```

Credential IDs are listed under the `ci-creds` / `ci-creds-infra` wrappers in
`jobs/ci-master.yaml`. `NEADER` and `S3LP3` no longer exist — the `s390x`/`arm64`
SSH-managed boxes are gone; delete any reference.

Freestyle infra jobs use `ci-creds-infra`, which is the subset the Ansible
playbook consumes.

### 5. Secret interpolation in `sh """..."""`

Groovy `${env.FOO_USR}` is substituted *before* the shell sees it — the secret is
baked into the script text and escapes Jenkins masking. Escape it so the shell
expands it at runtime:

```groovy
// wrong
sh """ git push https://${env.GITHUB_CREDS_USR}:${env.GITHUB_CREDS_PSW}@github.com/... """
// right
sh """ git push "https://\${GITHUB_CREDS_USR}:\${GITHUB_CREDS_PSW}@github.com/..." """
```

Prefer `sh '''...'''` (single-quoted, no Groovy interpolation) whenever the step
needs no Groovy values at all — that is what every stage in
`promote-charms.groovy` does.

### 6. Python / tox

`run-tox` used `python3.8`, which does not exist on noble. Replace with:

```groovy
                sh '''#!/bin/bash
                set -eux
                python3 -m venv venv
                venv/bin/python -m pip install tox
                venv/bin/tox --recreate -e py --notest
                '''
```

and in later stages activate it:

```groovy
                set +u
                source .tox/py/bin/activate
                set -u
                python jobs/<job>/main.py ...
```

Note the `tox -e py38 -- python ...` → `python ...` collapse: the venv is already
active, so drop the `tox -e py38 --` prefix entirely.

For freestyle jobs that still need it, `run-tox` → `run-venv` (which uses
`python3` and `tox -e py`).

### 7. LXD containers

- `ci_lxc_launch ubuntu:20.04 X` → `ci_lxc_launch ubuntu:24.04 X`.
- `ci_lxc_launch` in `cilib.sh` already injects the apt + snapd proxy into the
  container. Do not re-add proxy plumbing per job.
- Charmcraft containers: `ci_charmcraft_launch` (in
  `jobs/build-charms/charmcraft-lib.sh`) handles the git proxy fallback.
- The freestyle `trap 'ci_lxc_delete ...' EXIT` becomes a `post { always { ... } }`
  block guarded by `fileExists`, as in `build-charms.groovy`.
- Do not set `raw.idmap` — agents run as root, so uid/gid remapping is wrong.
- Do not set `bridge.mtu` / docker `mtu`.

### 8. Snapcraft

No host-level login. Snap-build jobs authenticate in-container using the
credential file pushed into it:

```groovy
sudo lxc shell ${lxc_name} -- bash -c \
    'export SNAPCRAFT_STORE_CREDENTIALS=\$(< "/snapcraft-creds"); '"snapcraft -v upload /\${BUILT_SNAP} --release ${params.channels}"
```

Delete every `snapcraft login --with`, `snapcraft whoami`, and `snapcraft logout`
call — host *and* container. Pin the snapcraft channel when installing:
`snap install snapcraft --channel=8.x/stable --classic`.

Do **not** add a `login to snapstore` task back into
`jobs/infra/playbook-jenkins.yml`; there is a `NOTE:` there explaining why.

### 9. Unsupported plugins

Remove from pipeline `options {}`:

```groovy
    options {
        ansiColor('xterm')   // DELETE - plugin not installed
        timestamps()         // DELETE - plugin not installed
        disableConcurrentBuilds()   // keep, core
    }
```

If the block becomes empty, delete the block. Freestyle `default-job-wrapper`
stays as-is.

### 10. Aggregating multi-command exit status

Freestyle jobs used `set +e` / `EXIT_STATUS=$?` / `exit $EXIT_STATUS` to run
several commands and fail once. In a pipeline, capture per-stage status and
evaluate at the end — see the `Build Charms` / `Build Bundles` / `Evaluate Result`
stages in `build-charms.groovy`:

```groovy
env.X_STATUS = sh(returnStatus: true, script: '''...''').toString()
// ... later
if (env.X_STATUS != '0') { error("...") }
```

### 11. Stages that cannot run on PS7

Do not silently delete. Comment the stage out with a `/* NOTE: (name) ... */`
block stating why and what the follow-up is — see `Process Images` in
`build-release-cdk-addons.groovy`.

### 12. Misc PS5-isms to strip

- `rm -rf /var/lib/jenkins/slaves/*/workspace/validate*` — gone.
- `wget` → `curl -fsSL -o` (wget is not in the trimmed apt set).
- `make ... 2>/dev/null` — keep stderr; PS7 failures are otherwise invisible.
- `GIT_SSH_COMMAND` pointing at `cdkbot_rsa` in `set-env` — removed.
- `columbo`, `tmpreaper`, `/etc/environment` provisioning — removed from the playbook.
- Float-parsed version comparisons (`Float.parseFloat("1.99")`) — use integer
  major/minor tokenisation, as fixed in `build-release-eks-snaps.groovy`.

## Remaining inventory

Files still referencing `runner-*` labels, in rough priority order:

| File | Jobs | Notes |
|---|---|---|
| `jobs/sync-oci-images.yaml` + `jobs/sync-oci-images/sync-oci-images.groovy` | `sync-oci-images` | already a pipeline; label + env + proxy only |
| `jobs/build-docs.yaml` + `jobs/build-docs/build-ck-docs.groovy` | `build-ck-docs` | already a pipeline |
| `jobs/aws-iam-docker/Jenkinsfile` | aws-iam-docker | already a pipeline |
| `jobs/validate-hacluster/Jenkinsfile` | validate-hacluster | already a pipeline |
| `jobs/sync-upstream.yaml` | `sync-snaps`, `sync-internal-tags`, `sync-upstream`, +4 | freestyle; several `disabled: true` — leave those disabled |
| `jobs/release-microk8s.yaml` | `release-microk8s*`, `update-microk8s-gh-branches-and-lp-builders` | matrix axis on `runner-cloud`; also container snapcraft login |
| `jobs/release-microk8s-capi.yaml` | `release-microk8s-capi` | freestyle |
| `jobs/validate.yaml`, `jobs/release.yaml` | `validate-*`, `validate-charm-*` | matrix jobs on `runner-validate`; largest blast radius, do last |
| `jobs/arc-conformance.yaml`, `jobs/cncf-conformance.yaml` | `conformance-*` | use `lxc-runner-params` + `run-lxc` |
| `jobs/build-debs.yaml`, `jobs/reports.yaml` | `build-debs`, `generate-reports-overview` | freestyle, low traffic |

`jobs/infra-ps5.yaml` is deleted; do not resurrect it.

## Verification

Every change must pass a local JJB render before it is considered done — this
catches bad macro names, broken `{}` escaping, and unknown project types without
touching the controller:

```bash
./.venv/bin/python -m jenkins_jobs test jobs/ -o /tmp/jjb-out
```

Expect `Number of jobs generated: 68` (grows/shrinks with the job count) and
exit 0. Inspect the rendered XML for the job you touched:

```bash
grep -n 'assignedNode\|scriptPath' /tmp/jjb-out/<job-name>
```

Watch for JJB brace escaping: inside a `job-template` or any macro with
`{param}` substitution, literal shell/Groovy braces must be doubled —
`${{HOME:-/var/lib/jenkins}}`, `%{{size_download}}`. A plain `- job:` needs no
doubling. A `KeyError`/`Unknown format code` from the render is almost always
this.

Publishing (requires `jobs/jjb-conf.ini`, template at
`jobs/jjb-conf.ini.example`, real values in BitWarden):

```bash
./.venv/bin/python -m jenkins_jobs --conf jobs/jjb-conf.ini update jobs/ci-master.yaml:jobs/<file>.yaml
```

Pipeline `.groovy` changes do **not** need a `jjb update` — the job pulls the
script from `ps7/main` at build time. YAML changes do.

## Acceptance for a migrated job

1. No `runner-*` label anywhere in the file.
2. Proxy env present (both cases) on every pipeline and every container it launches.
3. No `snapcraft login`/`logout`; store creds via `SNAPCRAFT_STORE_CREDENTIALS`.
4. No `python3.8`, no `tox -e py38`.
5. No `ansiColor`/`timestamps` in pipeline `options`.
6. No secret rendered through Groovy `${env.*_PSW}` inside a `"""` shell block.
7. Base images on `ubuntu:24.04`.
8. `jenkins-jobs test jobs/` exits 0 and the rendered XML shows the expected
   label and `scriptPath`.
9. Docs updated when job topology changes (`jobs/<job>/spec.yml` is the source
   for `docs/`; `mkdocs` destination is declared there).
