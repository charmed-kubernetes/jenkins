#!/bin/bash
set -eux
. ${WORKSPACE}/cilib.sh

# Map hosts paths into the container
LXC_HOME=/home/ubuntu
LXC_WORKSPACE=$LXC_HOME/workspace


ci_lxc_init_runner()
{
    # pass return variable to accept container name
    # automatically cleans up the container at the end
    # of the bash script unless "notrap" is passed

    # Usage:
    # ci_lxc_init_runner name_of_container [notrap] [use_vms] [cloud_egress]
    local  __resultvar=$1
    local  __trap=${2:-trap}
    local  __use_vms=${3:-false}
    local  __cloud_egress=${4:-false}

    # init a container runner on the build host
    local lxc_container=${JOB_NAME%%/*}-$(openssl rand -hex 10)-${BUILD_NUMBER}
    local lxc_apt_list=${LXC_APT_LIST:-}
    local lxc_snap_list=${LXC_SNAP_LIST:-}
    local lxc_push_list=${LXC_PUSH_LIST:-}
    local lxc_mount_list=${LXC_MOUNT_LIST:-}

    # prepare env file for runner
    declare -px > .env
    echo "declare -x HOME=${LXC_HOME}" >> ${WORKSPACE}/.env
    echo "declare -x HUDSON_HOME=${LXC_HOME}" >> ${WORKSPACE}/.env
    echo "declare -x JENKINS_HOME=${LXC_HOME}" >> ${WORKSPACE}/.env
    echo "declare -x PWD=${LXC_WORKSPACE}" >> ${WORKSPACE}/.env
    echo "declare -x WORKSPACE=${LXC_WORKSPACE}" >> ${WORKSPACE}/.env
    echo "declare -x WORKSPACE_TMP=${LXC_WORKSPACE}@tmp" >> ${WORKSPACE}/.env
    echo "declare -x PYTHONPATH=${LXC_WORKSPACE}:\"${PYTHONPATH:-}\"" >> ${WORKSPACE}/.env

    # ensure the container is torn down at the end of the job
    if [ "${__trap}" != "notrap" ]; then
       trap "ci_lxc_delete ${lxc_container}" EXIT
    fi

    # Start fresh container
    ci_lxc_delete ${lxc_container} || true

    # Maybe as a VM to avoid cgroup issues
    local vm_flag=""
    if [[ "${__use_vms,,}" == "true" ]]; then
        if sudo lxc info | grep 'driver: ' | grep -q 'qemu'; then
            vm_flag="--vm"
        else
            echo "ERROR: VM mode requested but QEMU driver is not available. LXC does not support VMs on this host."
            exit 1
        fi
    fi

    ci_lxc_launch ubuntu:24.04 ${lxc_container} ${vm_flag}

    # Install runtime dependencies in the container
    # Install debs, replacing semicolons with spaces
    ci_lxc_apt_install_retry ${lxc_container} ${lxc_apt_list//,/ }

    # Install snaps and push paths and mount paths
    _IFS=${IFS} # restore IFS
    IFS=','

    # Mount the workspace.
    # The agent runs as root and the container is unprivileged (no raw.idmap),
    # so the ubuntu user in the container sees the root-owned workspace as
    # `other`; open it up so the job can write its results (venv, ci.log, ...).
    chmod -R a+rwX ${WORKSPACE}
    ci_lxc_mount ${lxc_container} workspace ${WORKSPACE} ${LXC_WORKSPACE}

    # Copy (rather than mount) the credential/config paths from the agent's
    # $HOME into the ubuntu user's $LXC_HOME. They are root-owned secrets which
    # tools in the container (juju, aws) need to read and update.
    for mount_path in ${lxc_mount_list}; do
        if [ -d "${HOME}/${mount_path}" ]; then
            ci_lxc_push_tree ${lxc_container} ${HOME} ${mount_path} ${LXC_HOME}
        fi
    done

    for snap_args in ${lxc_snap_list}; do
        # snap_args could contain arguments separated by spaces
        # `juju --channel=2.9/stable` which requires splitting
        # on spaces to extract
        IFS=' ' read -a args <<< "$snap_args";
        ci_lxc_snap_install_retry ${lxc_container} ${args[@]} --classic < /dev/null
    done

    # push file paths from the host
    for push_path in ${lxc_push_list}; do
        ci_lxc_push ${lxc_container} ${push_path} ${push_path}
    done
    IFS=${_IFS} # restore IFS

    if [[ "${__cloud_egress,,}" == "true" ]]; then
        ci_lxc_cloud_egress ${lxc_container}
    fi

    eval $__resultvar="'$lxc_container'"
}


ci_lxc_cloud_egress()
{
    # PS7 has no direct route to the cloud networks. The egress proxy only lets
    # CONNECT through on a few ports (22, 443, 17070, 6443), and juju/ssh dial
    # the instances directly, ignoring HTTP proxy settings. Redirect vSphere and
    # the SSH/Juju/Kubernetes API ports of public cloud instances through
    # redsocks inside the container, reusing the release validation helper.
    local lxc_container=$1
    ci_lxc_apt_install_retry ${lxc_container} redsocks nftables
    ci_lxc_exec ${lxc_container} -- bash ${LXC_WORKSPACE}/jobs/release/container.sh egress
}


ci_lxc_job_run()
{
    # Run the job script inside the lxc runner
    local lxc_workspace=/home/ubuntu/workspace
    ci_lxc_exec_user --cwd=${lxc_workspace} --env WORKSPACE=${lxc_workspace} $@
}
