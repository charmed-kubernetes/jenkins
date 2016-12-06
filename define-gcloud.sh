# Define functions so scripts can use glcoud commands as if they were installed.

# Remove any old gcloud-config containers.
docker rm gcloud-config
# Are there any gcloud-config containers left?
CONFIG_CONTAINER=$(docker ps -a -q -f name=gcloud-config)

if [ -z $CONFIG_CONTAINER ]; then
  # Authorize 
  docker run \
    -v $GCE_ACCOUNT_CREDENTIAL:/root/gce.json \
    --name gcloud-config \
    google/cloud-sdk \
    gcloud auth activate-service-account \
    --key-file /root/gce.json \
    --project ubuntu-benchmarking
fi

# Use a docker container for the gcloud commands.
function gcloud {
  docker run \
    --rm \
    --volumes-from gcloud-config \
    google/cloud-sdk \
    gcloud "$@"
}

# Use a docker container for the gsutil commands.
function gsutil {
  docker run \
    --rm \
    --volumes-from gcloud-config \
    -v ${ARTIFACTS}:${ARTIFACTS} \
    google/cloud-sdk \
    gsutil $@
}
