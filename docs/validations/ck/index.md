# Verify CK
Verifies that CK passes integration tests

## Setup Phase
### Plugin: **runner** - Performs a snapd channel upgrade
This is ran with the validate-snapd-upgrade as the host snapd is also
upgraded to the new channel.

### Plugin: **juju** - Bootstrap and deploy kubernetes
## Plan Phase
### Plugin: **runner** - Run testsuite against deployed CK
### Plugin: **runner** - Performs an upgrade validation against a deployed CK
### Plugin: **runner** - Run testsuite against an upgrade snapcore
## Teardown Phase
### Plugin: **runner** - Teardown juju deployment
### Plugin: **runner** - Reset snapd back to stable
