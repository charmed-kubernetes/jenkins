import sh
import json

print(sh.sudo.apt("clean"))
print(sh.sudo.rm("-rf", "/var/log/*"))
print(sh.sudo.rm("-rf", "/var/lib/jenkins/.cache/*"))
print(sh.sudo.docker.image.prune('-a', '--filter', "until=24h", '--force'))
print(sh.sudo.docker.container.prune('--filter', "until=24h", '--force'))
print(sh.sudo.du('-h', '--max-depth=1', '/var/lib'))
print(sh.sudo.df('-h'))

containers = json.loads(sh.sudo.lxc.query('/1.0/containers').stdout.decode())
print(containers)
for container in containers:
    sh.sudo.lxc.delete('--force', container)

storage_pools = json.loads(sh.sudo.lxc.query('/1.0/storage-pools').stdout.decode())
print(storage_pools)
for storage in storage_pools:
    storage_name = storage.split('/')[-1]
    volumes = json.loads(sh.sudo.lxc.query(f"/1.0/storage-pools/{storage_name}/volumes").stdout.decode())
    print(volumes)
    for volume in volumes:
        volume_name = volume.split('/')[-1]
        print(f"Deleting {volume_name}")
        print(sh.sudo.lxc.storage.volume.delete(storage_name, f"custom/{volume_name}"))
    try:
        sh.sudo.lxc.storage.delete(storage_name)
    except sh.ErrorReturnCode_1 as e:
        print(f"Error removing {e}, continuing...")
