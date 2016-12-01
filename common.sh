#!/usr/bin/env bash 
# A common script to define functions and variables.

# A full path to the location of the JUJU_DATA.
JUJU_DATA="${JUJU_DATA:-$HOME/.local/share/juju}"
# The workspace directory to volume mount inside the docker container.
WORKSPACE="${WORKSPACE:-$PWD}"

# A function to run a command in the jujubox container.
function in-jujubox {
  command=$@
  # Format the command to run inside the container.
  docker run \
    --rm \
    -v ${JUJU_DATA}:${WORKSPACE}/juju \
    -v ${WORKSPACE}:/home/ubuntu/workspace \
    jujusolutions/jujubox:latest \
    sh -c "${command}"
}

# A function to make juju commands run inside a container.
function juju {
  args=$@
  # Call the function that runs the commands in a jujubox container.
  in-jujubox juju ${args}
}
