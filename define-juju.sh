# Define functions so scripts can use juju commands as if they were installed.

# A function to run a command in the jujubox container.
function in-jujubox {
  local command=$@
  # Format the command to run inside the container.
  docker run \
    --rm \
    -v ${JUJU_DATA}:/home/ubuntu/.local/share/juju \
    -v ${WORKSPACE}:/home/ubuntu/workspace \
    --entrypoint /bin/bash \
    jujusolutions/jujubox:latest \
    -c "${command}"
}

# A function to make juju commands run inside a container.
function juju {
  local args=$@
  # Call the function that runs the commands in a jujubox container.
  in-jujubox juju ${args}
}
