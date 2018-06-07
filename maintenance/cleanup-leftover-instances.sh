#!/usr/bin/env bash
set -eux

# 2920 is a stuck model that just hangs... :( We should fix that and remove that last grep
AWS_MODELS=$(juju models -c jenkins-ci-aws|grep cdk-build|awk '{print $1}'|grep -v '*'|grep -v 2920|cat)
GCE_MODELS=$(juju models -c jenkins-ci-google|grep cdk-build|awk '{print $1}'|grep -v '*'|cat)

echo "destroying AWS models:"
echo $AWS_MODELS
for model in $AWS_MODELS; do
  juju destroy-model -y jenkins-ci-aws:$model
done

echo "destroying GCE models:"
echo $GCE_MODELS
for model in $GCE_MODELS; do
  juju destroy-model -y jenkins-ci-google:$model
done
