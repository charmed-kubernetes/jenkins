#!/bin/bash
set -eu

# This script will generate a PR for upstream kubernetes(https://github.com/kubernetes/kubernetes) containing the
# latest commits from the https://github.com/juju-solutions/kubernetes fork.

# build up the PR message
echo <<EOF
**What this PR does / why we need it**:
Juju updates

**Release note**:
EOF

# grab the commit history
GIT_HISTORY=$(git log --pretty=format:"%s %b - %aN <%aE> %ad" staging..master > pr_message.txt)

# build up the PR message

cat << EOF > pr_message.txt
**What this PR does / why we need it**:
Juju updates

**Release note**:
```release-note
${GIT_HISTORY}
```
EOF

# we do this by rebasing master to the staging branch and then generating a PR from staging to upstream
git checkout staging
git rebase master

# now generate the PR - note that this requires GITHUB_TOKEN set to an access token with repo permissions
hub pull-request --file pr_message.txt -b upstream:master
