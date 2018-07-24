#!/bin/bash
set -eu

# This script will update juju-solutions/kubernetes with content from kubernetes. It will attempt a merge
# which should work for us since we should be the only one changing charm code.
# In the rare case that the merge fails, we can manually merge. The Jenkins job will notify via IRC when it fails.

git checkout master
if ! git remote|grep upstream; then
  git remote add upstream https://github.com/kubernetes/kubernetes.git
fi
git pull upstream master
git merge upstream/master
git push https://${CDKBOT_LOGIN}@github.com/juju-solutions/kubernetes master
