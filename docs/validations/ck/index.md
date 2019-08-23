# Verify CK
Verifies that CK passes integration tests

## Setup Phase
### Plugin: **juju** - Bootstrap and deploy kubernetes
## Plan Phase
### Plugin: **runner** - Run testsuite against deployed CK
### Plugin: **runner** - Performs an upgrade validation against a deployed CK
## Teardown Phase
### Plugin: **runner** - Get CDK Field Agent
### Plugin: **runner** - Teardown juju deployment
