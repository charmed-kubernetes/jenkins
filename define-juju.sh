# Define common Juju functions such as jujubox and charmbox.

# A function to run a command in the charmbox container.
function in-charmbox() {
  local command=$@
  docker run \
    --rm \
    -v ${JUJU_DATA}:/home/ubuntu/.local/share/juju \
    -v ${JUJU_REPOSITORY}:/home/ubuntu/charms \
    -v ${WORKSPACE}:/home/ubuntu/workspace \
    --entrypoint /bin/bash \
    jujusolutions/charmbox:latest \
    -c "${command}"
}

# A function to make charm commands run inside a container.
function charm() {
  local args=$@
  in-charmbox charm ${args}
}

# A function to run a command in the jujubox container.
function in-jujubox() {
  local command=$@
  docker run \
    --rm \
    -v ${JUJU_DATA}:/home/ubuntu/.local/share/juju \
    -v ${JUJU_REPOSITORY}:/home/ubuntu/charms \
    -v ${WORKSPACE}:/home/ubuntu/workspace \
    --entrypoint /bin/bash \
    jujusolutions/jujubox:latest \
    -c "${command}"
}

# A function to make juju commands run inside a container.
function juju() {
  local args=$@
  # Call the function that runs the commands in a jujubox container.
  in-jujubox juju ${args}
}
