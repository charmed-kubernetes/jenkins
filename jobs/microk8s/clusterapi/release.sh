#!/bin/bash

set -xe

#################################################################
## Description:
## - Fetches Git repositories from bootstrap and control plane providers, builds controllers,
##   and releases.
## - Release means pushing Docker images to DockerHub and tags to GitHub repositories.
##   There is a GitHub action configured on the repositories to create a release on tag push.

## Assumptions
## - Runs in an LXD environment where Docker and MicroK8s can be installed

## Limitations
## - Currently does not do any integration testing

## Requirements
## - docker
## - git
## - build-essential

## Credentials
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
echo "Build Docker images and release manifests from the checked out source code"

git clone https://github.com/canonical/cluster-api-bootstrap-provider-microk8s bootstrap -b "${BOOTSTRAP_PROVIDER_CHECKOUT}"
git clone https://github.com/canonical/cluster-api-control-plane-provider-microk8s control-plane -b "${CONTROL_PLANE_PROVIDER_CHECKOUT}"


#################################################################
if [ "${RUN_TESTS}" = true ]
then
    echo "Run tests"
    sudo snap install go --classic --channel=1.18/stable
    (
        cd bootstrap
        make fmt
        make vet
        # TODO: actually do testing
        # make lint
        # make test
    )
    (
        cd control-plane
        make fmt
        make vet
        # TODO: actually do testing
        # make lint
        # make test
    )
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
        git tag ${RELEASE_TAG}
        git push "https://${CDKBOT_GH_USR}:${CDKBOT_GH_PSW}@github.com/canonical/cluster-api-bootstrap-provider-microk8s" "${BOOTSTRAP_PROVIDER_CHECKOUT}" --tags
    )

    # create github release for control plane provider
    (
        cd control-plane
        git tag ${RELEASE_TAG}
        git push "https://${CDKBOT_GH_USR}:${CDKBOT_GH_PSW}@github.com/canonical/cluster-api-control-plane-provider-microk8s" "${CONTROL_PLANE_PROVIDER_CHECKOUT}" --tags
    )
fi
