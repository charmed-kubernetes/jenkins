# Usage:
#   source utils/retry.sh
#   retry <command>
#
# Run <command>, retrying up to 3 times if it fails.

retry() {
  (set +e
    for i in $(seq 3); do
      "$@"
      exit_code="$?"
      if [ "$exit_code" -eq 0 ]; then
        return 0
      fi
      sleep 1
    done
    echo "Command failed after 3 attempts: $@"
    return "$exit_code"
  )
}
