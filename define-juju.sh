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

# Print a string for the charm identifier given the id, series, and name.
function charm_id() {
  local id=$1
  local series=$2
  local charm_name=$3
  # The series is optional, check the second parameter for non empty string
  if [[ -n "${series}" ]]; then
    echo "cs:~${id}/${series}/${charm_name}"
  else
    echo "cs:~${id}/${charm_name}"
  fi
}

# Print a string of resources that exist for this charm.
function charm_resources() {
  local charm_id=$1
  # There is a bug with the attach where resources always go to unpublished.
  local show_cmd="charm show --channel=unpublished ${charm_id} resources"
  echo `${show_cmd} | grep -E 'Name:|Revision:' | awk '{print $2}' | paste - - | tr [:blank:] '-'`
  # charm show cs:~containers/kubernetes-e2e resources | grep -E 'Name:|Revision:' | awk '{print $2}' | paste - - | tr [:blank:] '-'
  # charm show ~containers/kubernetes-e2e resources --format json | jq -r '.resources[] | [.Name,.Revision|tostring] | join("-")'
}

# Push a directory to the charm store, release it and grant everyone access.
function charm_push_release() {
  local charm_build_dir=$1
  shift
  local charm_id=$1
  shift
  local channel=$1
  shift

  local channel_flag=""
  # The channel is optional, check the third parameter for non empty string.
  if [[ -n "${channel}" ]]; then
    channel_flag="--channel=${channel}"
  fi

  local resources=""
  # Loop through the remaining parameters for potentially multiple resources.
  for resource in "$@"; do
    # Resources should be in the name=value touple per parameter.
    resources="${resources} --resource ${resource}"
  done

  # Build the charm push command from the variables.
  local push_cmd="charm push ${charm_build_dir} ${charm_id} ${resources}"
  # Run the push command and capture the id of the pushed charm.
  local pushed_charm=`${push_cmd} | head -1 | awk '{print $2}'`
  # Release the charm to the specific channel.
  charm release ${pushed_charm} ${channel_flag}
  # Grant everyone read access to this charm in channel.
  charm grant ${pushed_charm} ${channel_flag} everyone
}
