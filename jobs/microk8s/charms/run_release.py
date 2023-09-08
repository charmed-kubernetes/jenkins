import os
from utils import ReleaseHelper

## - REPOSITORY: Repository to pull the MicroK8s charm code from
## - TAG: Tag to checkout
## - CHARM_NAME: Name of MicroK8s charm (default: microk8s)
## - CLUSTER_SIZE: Cluster size for the integration tests.
## - SNAP_CHANNELS: MicroK8s snap channels to test (space separated list).
## - SKIP_TESTS: Skip tests for promoting release (NOT RECOMMENDED).
## - SKIP_RELEASE: Skip promoting build to TO_CHANNEL after tests succeed.
## - JOB_NAME: from jenkins
## - BUILD_NUMBER: from jenkins

## - FROM_CHANNEL: Run integration tests against this channel. (default: edge)
## - TO_CHANNEL: After tests pass, charm will be pushed to this channel. (default: stable)
## - SERIES: Run tests for these OS series (space separated list) (default: focal jammy).


def main():
    series = os.environ.get("SERIES", "jammy")
    arch = os.environ.get("ARCH", "amd64")
    from_channel = os.environ.get("FROM_CHANNEL", "latest/edge")
    to_channel = os.environ.get("TO_CHANNEL", "latest/beta")
    skip_tests_env = os.environ.get("SKIP_TESTS", "false")
    skip_tests = skip_tests_env == "true"
    dry_run_env = os.environ.get("DRY_RUN", "true")
    dry_run = dry_run_env == "true"
    tests_repo = os.environ.get("REPOSITORY", "https://github.com/canonical/charm-microk8s")
    tests_branch = os.environ.get("BRANCH", "master")
    if to_channel.startswith("1."):
        version = to_channel.split("/")[0]
        tests_branch = f"release-{version}"

    release_helper = ReleaseHelper(series, arch)

    # Check if we need to release
    if not release_helper.is_release_needed(from_channel, to_channel) \
        and not release_helper.force_release:
        print(
            f"[{series} - {arch}][{from_channel} -> {to_channel}] Release is not required."
        )
        exit(0)
    
    # Run tests
    print(f"[{series} - {arch}][{from_channel} -> {to_channel}] Release process started.")
    if not skip_tests:
        print(
            f"[{series} - {arch}][{from_channel} -> {to_channel}] Tests taken from {tests_repo} in branch {tests_branch}."
        )

        if not release_helper.run_integration_tests(from_channel, tests_repo, tests_branch):
            print(
                f"[{series} - {arch}][{from_channel} -> {to_channel}] Tests failed, stopping release process."
            )
            exit(1)

    # Release
    if dry_run:
        print(f"[{series} - {arch}][{from_channel} -> {to_channel}] Dry run: releasing...")
    else:
        print(f"[{series} - {arch}][{from_channel} -> {to_channel}] Releasing...")
        release_helper.do_release(from_channel, to_channel)


if __name__ == "__main__":
    main()
