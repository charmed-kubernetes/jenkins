import sh
import json
containers = sh.sudo.lxc.list('--format', 'json').stdout.decode()
for container in containers:
    for line in sh.sudo.lxc.delete('--force', container['name'], _iter=True, _bg_exc=False):
        print(line)
