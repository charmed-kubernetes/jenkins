import click
from utils import ReleaseHelper, Configuration


def echo(config, msg):
    header = f"[{config.series} - {config.arch}][{config.from_channel} -> {config.to_channel}]"
    click.echo(f"{header} {msg}")


def main():
    config = Configuration()
    config.print()
    if not config.valid():
        exit(2)

    release_helper = ReleaseHelper(config.series, config.arch)

    # Check if we need to release
    if not release_helper.is_release_needed(config.from_channel, config.to_channel):
        echo(config, "Release is not required.")
        exit(0)

    # Run tests
    echo(config, "Release process started.")
    if not config.skip_tests:
        echo(
            config,
            f"Tests taken from {config.tests_repo} in branch {config.tests_branch}.",
        )

        if not release_helper.run_integration_tests(
            config.from_channel, config.tests_repo, config.tests_branch, config.juju_controller
        ):
            echo(config, "Tests failed, stopping release process.")
            exit(1)

    # Release
    if config.dry_run:
        echo(config, "Dry run: releasing.")
    else:
        echo(config, "Releasing.")
        release_helper.do_release(config.from_channel, config.to_channel)


if __name__ == "__main__":
    main()
