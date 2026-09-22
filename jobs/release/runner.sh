#!/bin/bash
# Private root-container runner for release validation.
set -euo pipefail

usage() {
    echo "usage: $0 {prepare|python|validate SCENARIO ARG...|collect|cleanup}" >&2
    exit 2
}

require_env() {
    local name
    for name in "$@"; do
        [[ -n ${!name:-} ]] || { echo "missing required environment: $name" >&2; exit 2; }
    done
}

require_file() {
    local name=$1 path=${!1:-}
    [[ -n $path && -r $path && -f $path ]] || {
        echo "missing readable credential file: $name" >&2
        exit 2
    }
}

require_env WORKSPACE LXC_NAME JUJU_CONTROLLER JUJU_CHANNEL CELL_NAME
[[ -d $WORKSPACE ]] || { echo "WORKSPACE is not a directory: $WORKSPACE" >&2; exit 2; }

lxc_exists() {
    local listing
    listing=$(sudo lxc list --format json) || {
        echo "unable to list LXD containers" >&2
        return 2
    }
    jq -e --arg name "$LXC_NAME" 'any(.[]; .name == $name)' >/dev/null <<<"$listing"
}

require_our_container() {
    lxc_exists || {
        local status=$?
        (( status == 1 )) && { echo "container does not exist: $LXC_NAME" >&2; return 1; }
        return "$status"
    }
    local tag
    tag=$(sudo lxc config get "$LXC_NAME" user.release-validation-id) || return
    [[ $tag == "$LXC_NAME" ]] || {
        echo "refusing untagged or mismatched container: $LXC_NAME" >&2
        return 1
    }
}

container_action() {
    sudo lxc exec "$LXC_NAME" --user 0 --group 0 --cwd /root/workspace -- \
        env -i \
        HOME=/root WORKSPACE=/root/workspace JUJU_DATA=/root/.local/share/juju TMPDIR=/root/tmp \
        PYTHONPATH=/root/workspace INTEGRATION_TEST_PATH=/root/workspace/jobs/integration \
        PATH=/snap/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin \
        LC_ALL=C.UTF-8 LANG=C.UTF-8 \
        HTTP_PROXY=http://egress.ps7.internal:3128 HTTPS_PROXY=http://egress.ps7.internal:3128 \
        http_proxy=http://egress.ps7.internal:3128 https_proxy=http://egress.ps7.internal:3128 \
        NO_PROXY=localhost,127.0.0.1 no_proxy=localhost,127.0.0.1 \
        JUJU_CONTROLLER="$JUJU_CONTROLLER" JUJU_OWNER=k8sci JOB_REPORTING=yes JOB_STAGE= STAGE= \
        TEST_UPGRADE_SNAPD_CHANNEL= \
        bash /root/workspace/jobs/release/container.sh "$@"
}

prepare() {
    require_file JUJUCREDS
    require_file JUJUCLOUDS
    require_file AWSCREDS
    require_file SSOCREDS

    if lxc_exists; then
        echo "container name collision: $LXC_NAME" >&2
        exit 1
    else
        local status=$?
        (( status == 1 )) || exit "$status"
    fi

    # ci_lxc_launch also configures the PS7 package and snap proxies.
    # Its argument handling is only used here with fixed image/name/config values.
    # shellcheck disable=SC1091
    source "$WORKSPACE/cilib.sh"
    set +x
    ci_lxc_launch ubuntu:24.04 "$LXC_NAME" "--config=user.release-validation-id=$LXC_NAME"
    ci_lxc_apt_install_retry "$LXC_NAME" python3-pip python3-venv python3-dev libffi-dev git curl openssh-client uuid-runtime jq libarchive-tools procps
    ci_lxc_snap_install_retry "$LXC_NAME" kubectl --classic
    ci_lxc_snap_install_retry "$LXC_NAME" juju-wait --classic
    ci_lxc_snap_install_retry "$LXC_NAME" juju-crashdump --classic
    sudo lxc exec "$LXC_NAME" -- snap install juju "--channel=$JUJU_CHANNEL"

    sudo lxc exec "$LXC_NAME" -- mkdir -p /root/workspace /root/tmp /root/.local/share/juju /root/.aws /root/.ssh
    sudo lxc exec "$LXC_NAME" -- chmod 700 /root/.local/share/juju /root/.aws /root/.ssh
    tar -C "$WORKSPACE" --exclude='__pycache__' -cf - \
        ci.bash juju.bash tox.ini requirements.txt requirements-2.9.txt pytest.ini \
        cilib bin jobs/release jobs/integration jobs/templates jobs/includes | \
        sudo lxc exec "$LXC_NAME" -- bsdtar -xf - --no-same-owner -C /root/workspace

    local archive
    for archive in JUJUCREDS JUJUCLOUDS; do
        sudo lxc file push "${!archive}" "$LXC_NAME/root/tmp/$archive"
        sudo lxc exec "$LXC_NAME" -- chown root:root "/root/tmp/$archive"
        sudo lxc exec "$LXC_NAME" -- chmod 600 "/root/tmp/$archive"
        sudo lxc exec "$LXC_NAME" -- bsdtar -xf "/root/tmp/$archive" -C /root/.local/share/juju --no-same-owner
        sudo lxc exec "$LXC_NAME" -- rm -f "/root/tmp/$archive"
    done
    sudo lxc file push "$AWSCREDS" "$LXC_NAME/root/.aws/credentials"
    sudo lxc file push "$SSOCREDS" "$LXC_NAME/root/.local/share/juju/store-usso-token"
    sudo lxc file push "$WORKSPACE/jobs/infra/fixtures/ssh_config" "$LXC_NAME/root/.ssh/config"
    sudo lxc exec "$LXC_NAME" -- chown root:root /root/.aws/credentials /root/.local/share/juju/store-usso-token /root/.ssh/config
    sudo lxc exec "$LXC_NAME" -- chmod 600 /root/.aws/credentials /root/.local/share/juju/store-usso-token /root/.ssh/config

    sudo lxc exec "$LXC_NAME" -- test -s /root/.local/share/juju/credentials.yaml || { echo "credential extraction failed: JUJUCREDS" >&2; exit 1; }
    sudo lxc exec "$LXC_NAME" -- test -s /root/.local/share/juju/clouds.yaml || { echo "credential extraction failed: JUJUCLOUDS" >&2; exit 1; }
    sudo lxc exec "$LXC_NAME" -- test -s /root/.aws/credentials || { echo "credential copy failed: AWSCREDS" >&2; exit 1; }
    sudo lxc exec "$LXC_NAME" -- test -s /root/.local/share/juju/store-usso-token || { echo "credential copy failed: SSOCREDS" >&2; exit 1; }
    local credential
    for credential in /root/.local/share/juju/credentials.yaml /root/.local/share/juju/clouds.yaml /root/.aws/credentials /root/.local/share/juju/store-usso-token; do
        [[ $(sudo lxc exec "$LXC_NAME" -- stat -c '%u:%g:%a' "$credential") == "0:0:600" ]] || exit 1
    done
    for credential in /root/.local/share/juju /root/.aws; do
        [[ $(sudo lxc exec "$LXC_NAME" -- stat -c '%u:%g:%a' "$credential") == "0:0:700" ]] || exit 1
    done
    sudo lxc exec "$LXC_NAME" -- test "$(sudo lxc exec "$LXC_NAME" -- id -u)" = 0
    sudo lxc exec "$LXC_NAME" -- test -w /root/workspace
    sudo lxc exec "$LXC_NAME" -- test -w /root/tmp

    sudo lxc exec "$LXC_NAME" -- juju --version >/dev/null
}
validate() {
    local scenario=${1:-}
    case $scenario in
        bugfix) [[ $# == 4 ]] || usage ;;
        bugfix-upgrade|release-upgrade) [[ $# == 5 ]] || usage ;;
        *) usage ;;
    esac
    require_our_container
    container_action validate "$@"
}

collect() {
    require_our_container || return $?
    local destination="$WORKSPACE/results/$CELL_NAME" item source
    mkdir -p "$destination"
    for item in ci.log metadata.json metadata.db report.html report.json report.xml artifacts.tar.gz meta failures logs _out; do
        source="/root/workspace/$item"
        if sudo lxc exec "$LXC_NAME" -- test -e "$source"; then
            if sudo lxc exec "$LXC_NAME" -- test -d "$source"; then
                sudo lxc file pull -r "$LXC_NAME$source" "$destination/"
            else
                sudo lxc file pull "$LXC_NAME$source" "$destination/"
            fi
        fi
    done
    local crashdump
    while IFS= read -r crashdump; do
        sudo lxc file pull "$LXC_NAME/root/workspace/$crashdump" "$destination/"
    done < <(sudo lxc exec "$LXC_NAME" -- sh -c 'cd /root/workspace && for item in juju-crashdump*; do test -e "$item" && printf "%s\n" "$item"; done')
}

cleanup() {
    if lxc_exists; then
        :
    else
        local status=$?
        (( status == 1 )) && return 0
        return "$status"
    fi
    require_our_container
    local status=0
    local state
    state=$(sudo lxc info "$LXC_NAME" --format json | jq -r '.status') || status=$?
    if [[ $state == Stopped ]]; then
        sudo lxc start "$LXC_NAME" || status=$?
    fi
    if sudo lxc exec "$LXC_NAME" -- test -f /root/workspace/jobs/release/container.sh; then
        container_action cleanup || status=$?
        collect || status=$?
    fi
    sudo lxc delete --force "$LXC_NAME" || status=$?
    return "$status"
}

case ${1:-} in
    prepare) [[ $# == 1 ]] || usage; prepare ;;
    python) [[ $# == 1 ]] || usage; require_our_container; container_action python ;;
    validate) shift; validate "$@" ;;
    cleanup) [[ $# == 1 ]] || usage; cleanup ;;
    *) usage ;;
esac
