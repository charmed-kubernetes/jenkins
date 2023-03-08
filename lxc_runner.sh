#!/bin/bash
set -eux
. ${WORKSPACE}/cilib.sh

# Map hosts paths into the container
LXC_HOME=/home/ubuntu
LXC_WORKSPACE=$LXC_HOME/workspace
LXC_JUJU=$LXC_HOME/.local/share/juju
LXC_AWS=$LXC_HOME/.aws
LXC_SSH=$LXC_HOME/.ssh


ci_lxc_init_runner()
{
    # pass return variable to accept container name
    # Usage:
    # ci_lxc_init_runner name_of_container
    local  __resultvar=$1 

    # init a container runner on the build host
    local lxc_container=${JOB_NAME%%/*}-$(openssl rand -hex 20)-${BUILD_NUMBER}
    local lxc_apt_list=${LXC_APT_LIST:-}
    local lxc_snap_list=${LXC_SNAP_LIST:-}
    local lxc_push_list=${LXC_PUSH_LIST:-}

    # prepare env file for runner
    declare -px > .env
    echo "declare -x HOME=${LXC_HOME}" >> ${WORKSPACE}/.env
    echo "declare -x HUDSON_HOME=${LXC_HOME}" >> ${WORKSPACE}/.env
    echo "declare -x JENKINS_HOME=${LXC_HOME}" >> ${WORKSPACE}/.env
    echo "declare -x PWD=${LXC_WORKSPACE}" >> ${WORKSPACE}/.env
    echo "declare -x TMPDIR=${LXC_WORKSPACE}/tmp" >> ${WORKSPACE}/.env
    echo "declare -x WORKSPACE=${LXC_WORKSPACE}" >> ${WORKSPACE}/.env
    echo "declare -x WORKSPACE_TMP=${LXC_WORKSPACE}@tmp" >> ${WORKSPACE}/.env
    echo "declare -x PYTHONPATH=${LXC_WORKSPACE}:\"${PYTHONPATH:-}\"" >> ${WORKSPACE}/.env

    # ensure the container is torn down at the end of the job
    trap "ci_lxc_delete ${lxc_container}" EXIT

    # Start fresh container
    ci_lxc_delete ${lxc_container} || true
    ci_lxc_launch ubuntu:22.04 ${lxc_container}

    # Mount the mapped paths
    ci_lxc_mount ${lxc_container} workspace ${WORKSPACE} ${LXC_WORKSPACE}
    ci_lxc_mount ${lxc_container} juju $HOME/.local/share/juju ${LXC_JUJU}
    ci_lxc_mount ${lxc_container} aws $HOME/.aws ${LXC_AWS}
    ci_lxc_mount ${lxc_container} ssh $HOME/.ssh ${LXC_SSH}

    # Install runtime dependencies in the container
    # Install debs, replacing semicolons with spaces
    ci_lxc_apt_install ${lxc_container} ${lxc_apt_list//,/ }

    # Install snaps and push paths
    _IFS=${IFS} # restore IFS
    IFS=','
    for snap_args in ${lxc_snap_list}; do
        # snap_args could contain arguments separated by spaces
        # `juju --channel=2.9/stable` which requires splitting
        # on spaces to extract
        IFS=' ' read -a args <<< "$snap_args"; 
        ci_lxc_snap_install ${lxc_container} ${args[@]} --classic < /dev/null
    done

    # push file paths from the host
    for push_path in ${lxc_push_list}; do
        ci_lxc_push ${lxc_container} ${push_path} ${push_path}
    done
    IFS=${_IFS} # restore IFS

    eval $__resultvar="'$lxc_container'"
}


ci_lxc_job_run()
{
    # Run the job script inside the lxc runner
    local lxc_workspace=/home/ubuntu/workspace
    ci_lxc_exec_user --cwd=${lxc_workspace} --env WORKSPACE=${lxc_workspace} $@
}