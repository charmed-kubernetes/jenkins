import sh
import json
containers = sh.contrib.sudo.lxc.list('--format', 'json').stdout.decode()
for container in containers:
    for line in sh.contrib.sudo.lxc.delete('--force', container['name'], _iter=True, _bg_exc=False):
        print(line)
