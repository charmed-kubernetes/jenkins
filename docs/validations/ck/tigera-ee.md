# Verify CK with Tigera
Verifies that CK with Tigera passes integration tests

## Setup Phase
### Plugin: **runner** - Cleanup any previous artifacts
### Plugin: **juju** - Bootstrap and deploy kubernetes
### Plugin: **runner** - Prep environment for Tigera testing
## Plan Phase
### Plugin: **runner** - Run testsuite against deployed CK
## Teardown Phase
### Plugin: **runner** - Teardown juju deployment
