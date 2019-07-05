# Validate Juju HTTP(S) proxy test - Legacy

## Purpose

This tests' purpose is to test the proxy configuration keys.

This test is separate for the HTTP(s) proxy tests due to change where layer-docker has been effectively deprecated.

## Charm(s) tested:

- layer-docker
- kubernetes-worker
- kubernetes-master

## Files tested

- `/lib/systemd/system/docker.service`

## Steps
*Cluster spin up*

1. Adds a proxy to the model
2. Adds container runtime
3. Changes `juju-http(s)-proxy` configuration keys, then waits
4. SCPs configuration files from all units
5. Checks for existence of keys.
6. Clears configuration keys
7. Checks for missing keys
8. Repeats from 2. for all container runtimes.
