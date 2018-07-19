import os

# basic paths
home = os.getenv("HOME")
workdir = home + "/snap-builds"
snap_name = "microk8s"
# basic data
people_name = "microk8s-dev"
# we need to store credentials once for cronned builds
cachedir = workdir + "/cache"
creds = workdir + "/credentials"
