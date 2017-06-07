# CDK upgrade tests

## Install

Dependencies can be installed by running:
```
./install-deps.sh
```

## Running tests

This test suite assumes that a juju controller has already been bootstrapped.

Select the juju controller you want to use:
```
juju switch my-controller
```

To run all tests:
```
pytest
```

To run tests from a single file:
```
pytest test_upgrade_charms.py
```
