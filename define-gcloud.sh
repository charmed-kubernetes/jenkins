# Define functions so scripts can use glcoud commands as if they were installed.

# Use a docker container for the gcloud commands.
function gcloud {
  docker run \
    --rm \
    --name gcloud
    -v ${GCE_ACCOUNT_CREDENTIAL}:/root/gce.json \
    google/cloud-sdk \
    "gcloud $@"
}

# Use a docker container for the gsutil commands.
function gsutil {
  docker run \
    --rm \
    --name gsutil \
    -v ${GCE_ACCOUNT_CREDENTIAL}:/root/gce.json \
    -v ${ARTIFACTS}:${ARTIFACTS} \
    google/cloud-sdk \
    gsutil $@
}
