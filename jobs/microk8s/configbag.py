import os

tracks = ["latest", "1.10", "1.11", "1.12", "1.13", "1.14", "1.15"]

snap_name = "microk8s"
people_name = "microk8s-dev"
cachedir = os.getenv('WORKSPACE') + "/cache"
creds = os.getenv('LPCREDS')
