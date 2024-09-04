#!/bin/bash

set -xe

_DIR="${BASH_SOURCE%/*}"
if [[ ! -d "$_DIR" ]]; then _DIR="$PWD"; fi

#################################################################
## Description:
## - Fetches Git repositories from bootstrap and control plane providers, builds controllers,
##   spins up a test cluster on AWS and runs a few basic checks, then tears everything down
##   and releases.
## - Release means pushing Docker images to DockerHub and tags to GitHub repositories.
##   There is a GitHub action configured on the repositories to create a release on tag push.

## Assumptions
## - Runs in an LXD environment where Docker and MicroK8s can be installed

## Limitations
## - Currently does not do any integration testing
## - Currently does nothing to manage cleaning up stale AWS resources in case of failure

## Requirements
## - docker
## - git
## - build-essential

## Credentials
## - AWS (to run tests)
## - Git (to push tags to GitHub repositories)
## - DockerHub (to push images)

## Configuration
BOOTSTRAP_PROVIDER_CHECKOUT="${BOOTSTRAP_PROVIDER_CHECKOUT:-main}"              # commit to checkout from bootstrap provider
CONTROL_PLANE_PROVIDER_CHECKOUT="${CONTROL_PLANE_PROVIDER_CHECKOUT:-main}"      # commit to checkout from control plane provider
RELEASE_TAG="${RELEASE_TAG:-}"                                                  # release tag that will be pushed on success
SKIP_RELEASE="${SKIP_RELEASE:-false}"                                           # do not release if set to true
RUN_TESTS="${RUN_TESTS:-true}"                                                  # do not run the tests if set to false

if [ -z "${RELEASE_TAG}" ]
then
    echo "Please set a release tag even if no release is to be performed"
    exit 1
fi

#################################################################
echo "Check out source code"

git clone https://github.com/canonical/cluster-api-bootstrap-provider-microk8s bootstrap -b "${BOOTSTRAP_PROVIDER_CHECKOUT}"
git clone https://github.com/canonical/cluster-api-control-plane-provider-microk8s control-plane -b "${CONTROL_PLANE_PROVIDER_CHECKOUT}"

#################################################################
if [ "${RUN_TESTS}" = true ]
then
    docker login -u ${DOCKERHUB_USR} -p ${DOCKERHUB_PSW}

    echo "Run unit tests"

    sudo snap install go --channel 1.19 || sudo snap refresh go --channel 1.19
    (
        cd bootstrap
        make vet
        make lint
        make test
        make
    )
    (
        cd control-plane
        make vet
        make lint
        make test
        make
    )

    echo "Run integration tests"

    echo "Setup management cluster"
    sudo lxc profile create microk8s || true
    curl "https://raw.githubusercontent.com/canonical/microk8s/strict/tests/lxc/microk8s.profile" | sudo lxc profile edit microk8s

    sudo snap install kubectl --classic || sudo snap refresh kubectl

    # attempt to cleanup from previous runs
    (
        sudo lxc exec capi-tests -- microk8s kubectl delete cluster --all --timeout=10s || true
        sudo lxc rm capi-tests --force || true
    )
    sudo lxc launch ubuntu:22.04 -p default -p microk8s capi-tests
    sleep 10
    while ! sudo lxc exec capi-tests -- snap install microk8s --channel latest/beta --classic; do
        sleep 3
    done
    sudo lxc exec capi-tests -- microk8s status --wait-ready
    sudo lxc exec capi-tests -- microk8s enable rbac dns
    mkdir ~/.kube -p
    sudo lxc exec capi-tests -- microk8s config > ~/.kube/config

    # download clusterctl and install
    echo "Install clusterctl"
    curl -L https://github.com/kubernetes-sigs/cluster-api/releases/download/v1.2.4/clusterctl-linux-amd64 -o clusterctl
    chmod +x clusterctl
    sudo mv ./clusterctl /usr/local/bin/clusterctl
    clusterctl version

    # initialize infrastructure provider
    echo "Initialize AWS infrastructure provider"
    # requires sourced credentials AWS_B64ENCODED_CREDENTIALS. to refresh credentials, do
    # export AWS_REGION=us-west-1
    # export AWS_ACCESS_KEY_ID="${AWS_ACCESS_KEY_ID}"
    # export AWS_ACCESS_SECRET_KEY="${AWS_ACCESS_SECRET_KEY}"
    # clusterawsadm bootstrap iam create-cloudformation-stack
    # export AWS_B64ENCODED_CREDENTIALS=$(clusterawsadm bootstrap credentials encode-as-profile)
    clusterctl init --infrastructure aws --bootstrap - --control-plane -

    echo "Build Docker images and release manifests from the checked out source code"
    (
        cd bootstrap
        docker build -t cdkbot/capi-bootstrap-provider-microk8s:${RELEASE_TAG}-dev .
        docker push cdkbot/capi-bootstrap-provider-microk8s:${RELEASE_TAG}-dev
        sed "s,docker.io/cdkbot/capi-bootstrap-provider-microk8s:latest,docker.io/cdkbot/capi-bootstrap-provider-microk8s:${RELEASE_TAG}-dev," -i bootstrap-components.yaml
    )
    (
        cd control-plane
        docker build -t cdkbot/capi-control-plane-provider-microk8s:${RELEASE_TAG}-dev .
        docker push cdkbot/capi-control-plane-provider-microk8s:${RELEASE_TAG}-dev
        sed "s,docker.io/cdkbot/capi-control-plane-provider-microk8s:latest,docker.io/cdkbot/capi-control-plane-provider-microk8s:${RELEASE_TAG}-dev," -i control-plane-components.yaml
    )

    # deploy microk8s providers
    kubectl apply -f bootstrap/bootstrap-components.yaml -f control-plane/control-plane-components.yaml

    (
        cd bootstrap
        make e2e
    )

    # cleanup machine
    sudo lxc rm capi-tests --force || true
fi

#################################################################
if [ "${SKIP_RELEASE}" = false ]
then
    echo "Release"
    docker login -u ${DOCKERHUB_USR} -p ${DOCKERHUB_PSW}

    # build and push bootstrap provider images
    (
        cd bootstrap
        make docker-manifest IMG=cdkbot/capi-bootstrap-provider-microk8s:${RELEASE_TAG//v}
        make docker-manifest IMG=cdkbot/capi-bootstrap-provider-microk8s:latest
    )

    # build and push control-plane provider images
    (
        cd control-plane
        make docker-manifest IMG=cdkbot/capi-control-plane-provider-microk8s:${RELEASE_TAG//v}
        make docker-manifest IMG=cdkbot/capi-control-plane-provider-microk8s:latest
    )

    # create github release for bootstrap provider
    (
        cd bootstrap
        git tag "${RELEASE_TAG}"
        git push "https://${CDKBOT_GH_USR}:${CDKBOT_GH_PSW}@github.com/canonical/cluster-api-bootstrap-provider-microk8s" --tags "${RELEASE_TAG}"
    )

    # create github release for control plane provider
    (
        cd control-plane
        git tag "${RELEASE_TAG}"
        git push "https://${CDKBOT_GH_USR}:${CDKBOT_GH_PSW}@github.com/canonical/cluster-api-control-plane-provider-microk8s" --tags "${RELEASE_TAG}"
    )
fi
