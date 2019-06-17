#!/bin/bash

set -eux

echo "####### FS Usage (Start)"
df -h

echo "####### Cleaning up"
sudo apt-get clean || true
sudo rm -rf /var/log/* || true
sudo rm -rf /var/lib/jenkins/.cache/* || true
docker image prune -a --filter "until=24h" --force
docker container prune --filter "until=24h" --force

echo "####### Checking /var/lib"
sudo du -h --max-depth=1 /var/lib

echo "####### FS Usage (Finish)"
df -h


echo "####### Removing LXD cruft"
for i in `sudo lxc query /1.0/containers | jq -r '. | map(. | sub("/1.0/containers/"; "")) | join("\n")'`
do
    sudo lxc delete --force $i
done

for i in `sudo lxc query /1.0/storage-pools | jq -r '. | map(. | sub("/1.0/storage-pools/"; "")) | join("\n")' | grep -v default`
do
    for x in `sudo lxc query /1.0/storage-pools/$i/volumes |jq -r '. | map(. | sub("/1.0/storage-pools/$i/volumes/container/"; "") | sub("/1.0/storage-pools/$i/volumes/image/"; "")) | join("\n")' | grep -v default`
    do
        sudo lxc storage volume delete $i $x
    done
    sudo lxc storage delete $i

done
