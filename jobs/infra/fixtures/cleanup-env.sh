#!/bin/bash
set -x

for i in $(juju controllers --format json | jq -r '.controllers | keys[]'); do
    echo "$i"
    juju destroy-controller --destroy-all-models --destroy-storage -y "$i" 2>&1
done

sudo apt clean
sudo rm -rf /var/log/*
sudo rm -rf /var/lib/jenkins/.cache/*
docker image prune -a --filter until=24h --force
docker container prune --filter until=24h --force
rm -rf /var/lib/jenkins/venvs

# containers = json.loads(run("sudo lxc query /1.0/containers", shell=True, capture_output=True).stdout.decode())
# print(containers)
# for container in containers:
#     run("sudo lxc --force {}".format(container), shell=True)

# storage_pools = json.loads(run("sudo lxc query /1.0/storage-pools", shell=True, capture_output=True).stdout.decode())
# print(storage_pools)
# for storage in storage_pools:
#     storage_name = storage.split("/")[-1]
#     volumes = json.loads(
#         run("sudo lxc query /1.0/storage-pools/{}/volumes".format(storage_name), shell=True, capture_output=True).stdout.decode()
#     )
#     print(volumes)
#     for volume in volumes:
#         volume_name = volume.split("/")[-1]
#         print("Deleting {}".format(volume_name))
#         run("sudo lxc storage volume delete {} {}".format(storage_name, "custom/{}".format(volume_name)), shell=True)
#     try:
#         run("sudo lxc storage delete {}".format(storage_name))
#     except CalledProcessError as e:
#         print("Error removing {}, continuing...".format(e))
