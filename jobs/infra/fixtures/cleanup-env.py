import json
from subprocess import run, CalledProcessError

try:
    juju_controllers = json.loads(
        run(
            "juju controllers --format json", shell=True, capture_output=True
        ).stdout.decode()
    )
    if juju_controllers:
        for name, _ in juju_controllers:
            try:
                run(
                    "juju destroy-controller --destroy-all-models --destroy-storage -y {}".format(
                        name
                    ),
                    shell=True,
                )
            except CalledProcessError as e:
                print("Error destroying {}, continuing...".format(e))
except CalledProcessError as e:
    print("Error reading controller: {}, continuing...".format(e))


run("sudo apt clean", shell=True)
run("sudo rm -rf /var/log/*", shell=True)
run("sudo rm -rf /var/lib/jenkins/.cache/*", shell=True)
run("docker image prune -a --filter until=24h --force", shell=True)
run("docker container prune --filter until=24h --force", shell=True)

containers = json.loads(
    run(
        "sudo lxc query /1.0/containers", shell=True, capture_output=True
    ).stdout.decode()
)
print(containers)
for container in containers:
    run("sudo lxc --force {}".format(container), shell=True)

storage_pools = json.loads(
    run(
        "sudo lxc query /1.0/storage-pools", shell=True, capture_output=True
    ).stdout.decode()
)
print(storage_pools)
for storage in storage_pools:
    storage_name = storage.split("/")[-1]
    volumes = json.loads(
        run(
            "sudo lxc query /1.0/storage-pools/{}/volumes".format(storage_name),
            shell=True,
            capture_output=True,
        ).stdout.decode()
    )
    print(volumes)
    for volume in volumes:
        volume_name = volume.split("/")[-1]
        print("Deleting {}".format(volume_name))
        run(
            "sudo lxc storage volume delete {} {}".format(
                storage_name, "custom/{}".format(volume_name)
            ),
            shell=True,
        )
    try:
        run("sudo lxc storage delete {}".format(storage_name))
    except CalledProcessError as e:
        print("Error removing {}, continuing...".format(e))

run("rm -rf /var/lib/jenkins/venvs", shell=True)
