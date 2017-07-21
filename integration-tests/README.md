# CDK integration tests

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

To run charm tests:
```
pytest test_charms.py
```

To run tests against an existing deployment:
```
pytest test_live_model.py
```

In addition to the info in stdout, you can find additional data logged for each
test in the `logs` folder:
```
$ tree logs
logs
└── test_charms
    ├── test_bundletester
    │   ├── bundletester.xml
    │   └── canonical-kubernetes
    │       ├── bundle.yaml
    │       ├── README.md
    │       └── tests
    │           ├── 20-charm-validation.py
    │           ├── 30-unit-shuffle.py
    │           ├── 40-security-check.py
    │           ├── amulet_utils.py
    │           └── tests.yaml
    ├── test_deploy[kubernetes-core]
    │   ├── debug-log
    │   └── model-info
    └── test_upgrade[kubernetes-core]
        ├── debug-log
        └── model-info
```
