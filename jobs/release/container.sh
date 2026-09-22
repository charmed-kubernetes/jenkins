#!/bin/bash
# Dispatcher executed as root inside the private release-validation container.
set -euo pipefail

usage() {
    echo "usage: $0 {python|validate SCENARIO ARG...|cleanup}" >&2
    exit 2
}

require_workspace() {
    [[ -n ${WORKSPACE:-} && -d ${WORKSPACE:-} ]] || { echo "WORKSPACE is required" >&2; exit 2; }
    [[ -n ${TMPDIR:-} ]] || { echo "TMPDIR is required" >&2; exit 2; }
}

scenario_spec() {
    case $1 in
        bugfix) [[ $# == 4 ]] || usage; printf '%s\n' "$WORKSPACE/jobs/release/bugfix-spec" ;;
        bugfix-upgrade) [[ $# == 5 ]] || usage; printf '%s\n' "$WORKSPACE/jobs/release/bugfix-upgrade-spec" ;;
        release-upgrade) [[ $# == 5 ]] || usage; printf '%s\n' "$WORKSPACE/jobs/release/release-upgrade-spec" ;;
        *) usage ;;
    esac
}

prepare_python() {
    require_workspace
    cd "$WORKSPACE"
    python3 -m venv venv
    venv/bin/python -m pip install tox
    venv/bin/tox --recreate -e py --notest
}

validate() {
    require_workspace
    local scenario=${1:-}
    [[ -n $scenario ]] || usage
    local spec
    spec=$(scenario_spec "$@")
    [[ -f $spec ]] || { echo "missing allowlisted specification: $spec" >&2; exit 1; }
    [[ -f $WORKSPACE/.tox/py/bin/activate ]] || { echo "missing prepared Python environment" >&2; exit 1; }
    mkdir -p "$TMPDIR"
    local pid_file="$TMPDIR/release-validation.pid" pid status

    # Legacy activation reads optional variables; do not enable nounset around it.
    set +u
    # shellcheck disable=SC1090
    source "$WORKSPACE/.tox/py/bin/activate"
    set -u

    setsid bash "$spec" "${@:2}" &
    pid=$!
    printf '%s\n' "$pid" > "$pid_file"
    trap 'kill -TERM -- "-$pid" 2>/dev/null || true; wait "$pid" || true; rm -f "$pid_file"; exit 143' TERM INT
    set +e
    wait "$pid"
    status=$?
    set -e
    trap - TERM INT
    rm -f "$pid_file"
    return "$status"
}

terminate_validation_group() {
    local pid_file="$TMPDIR/release-validation.pid" pid remaining=30
    [[ -f $pid_file ]] || return 0
    read -r pid < "$pid_file" || return 1
    [[ $pid =~ ^[0-9]+$ ]] || { echo "invalid validation PID record" >&2; return 1; }
    if kill -0 -- "-$pid" 2>/dev/null; then
        kill -TERM -- "-$pid" || return 1
        while (( remaining > 0 )) && kill -0 -- "-$pid" 2>/dev/null; do
            sleep 1
            ((remaining--))
        done
        kill -0 -- "-$pid" 2>/dev/null && kill -KILL -- "-$pid"
    fi
    rm -f "$pid_file"
}

cleanup() {
    require_workspace
    terminate_validation_group
    command -v juju >/dev/null || return 0
    [[ -n ${JUJU_CONTROLLER:-} ]] || { echo "JUJU_CONTROLLER is required" >&2; return 1; }
    [[ -e ${JUJU_DATA:-/root/.local/share/juju}/controllers.yaml ]] || return 0

    local controllers
    controllers=$(juju controllers --format json) || { echo "unable to inspect Juju controller state" >&2; return 1; }
    if ! python3 -c 'import json, sys; sys.exit(0 if sys.argv[1] in json.load(sys.stdin) else 1)' "$JUJU_CONTROLLER" <<<"$controllers"; then
        return 0
    fi
    if ! timeout 2m juju destroy-controller --no-prompt --destroy-all-models --destroy-storage "$JUJU_CONTROLLER"; then
        timeout 10m juju kill-controller -t 2m0s --no-prompt "$JUJU_CONTROLLER"
    fi
}

case ${1:-} in
    python) [[ $# == 1 ]] || usage; prepare_python ;;
    validate) shift; validate "$@" ;;
    cleanup) [[ $# == 1 ]] || usage; cleanup ;;
    *) usage ;;
esac
