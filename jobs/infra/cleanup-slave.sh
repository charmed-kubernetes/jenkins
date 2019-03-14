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
