# Define common Juju functions such as jujubox and charmbox.

# A function to run a command in the charmbox container.
function in-charmbox() {
  docker run \
    --rm \
    -v ${JUJU_DATA}:/home/ubuntu/.local/share/juju \
    -v ${JUJU_REPOSITORY}:/home/ubuntu/charms \
    -v ${WORKSPACE}:/home/ubuntu/workspace \
    --entrypoint /bin/bash \
    jujusolutions/charmbox:latest \
    -c "$@"
}

# A function to make charm commands run inside a container.
function charm() {
  in-charmbox charm "$@"
}

# A function to run a command in the jujubox container.
function in-jujubox() {
  docker run \
    --rm \
    -v ${JUJU_DATA}:/home/ubuntu/.local/share/juju \
    -v ${WORKSPACE}:/home/ubuntu/workspace \
    --entrypoint /bin/bash \
    jujusolutions/jujubox:latest \
    -c "$@"
}

# A function to make juju commands run inside a container.
function juju() {
  # Call the function that runs the commands in a jujubox container.
  in-jujubox juju "$@"
}
