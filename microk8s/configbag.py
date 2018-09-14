import os

tracks = ["latest", "1.10", "1.11", "1.12", "1.13", "1.14", "1.15"]

# basic paths
home = os.getenv("HOME")
workdir = home + "/snap-builds"
snap_name = "microk8s"
# basic data
people_name = "microk8s-dev"
# we need to store credentials once for cronned builds
cachedir = workdir + "/cache"
creds = workdir + "/credentials"
