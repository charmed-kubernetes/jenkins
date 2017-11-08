function RUN() {
    lxc exec $container -- "$@"
}

function PUSH() {
    src="$1"
    dst="$(echo $2 | sed -e 's/^\///')"
    shift 2
    lxc file push "$src" $container/"$dst" "$@"
}


function container_exists() {
  if ! lxc list  | grep $container
  then
    echo "Container $container not found. Please select a container from the list below."
    lxc list
    exit 1
  fi
}
