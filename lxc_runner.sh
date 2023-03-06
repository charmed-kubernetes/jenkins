#!/bin/bash
set -eux
. ${WORKSPACE}/cilib.sh

# init a container runner on the build host
LXC_RUNNER_NAME=${BUILD_TAG}

# Map hosts paths into the container
LXC_HOME=/home/ubuntu
LXC_WORKSPACE=$LXC_HOME/workspace
LXC_JUJU=$LXC_HOME/.local/share/juju
LXC_AWS=$LXC_HOME/.aws
LXC_SSH=$LXC_HOME/.ssh


ci_lxc_init_runner()
{
    # prepare env file for runner
    echo 'function runner(){ echo ignored; }' > .env
    env >> .env
    echo "HOME=${LXC_HOME}" >> .env
    echo "HUDSON_HOME=${LXC_HOME}" >> .env
    echo "JENKINS_HOME=${LXC_HOME}" >> .env
    echo "PWD=${LXC_WORKSPACE}" >> .env
    echo "WORKSPACE=${LXC_WORKSPACE}" >> .env
    echo "WORKSPACE_TMP=${LXC_WORKSPACE}@tmp" >> .env
    echo "PYTHONPATH=${LXC_WORKSPACE}:\"${PYTHONPATH:-}\"" >> .env

    # ensure the container is torn down at the end of the job
    trap "ci_lxc_delete ${LXC_RUNNER_NAME}" EXIT

    # Start fresh container
    ci_lxc_delete ${LXC_RUNNER_NAME} || true
    ci_lxc_launch ubuntu:22.04 ${LXC_RUNNER_NAME}

    # Mount the mapped paths
    ci_lxc_mount ${LXC_RUNNER_NAME} workspace ${WORKSPACE} ${LXC_WORKSPACE}
    ci_lxc_mount ${LXC_RUNNER_NAME} juju $HOME/.local/share/juju ${LXC_JUJU}
    ci_lxc_mount ${LXC_RUNNER_NAME} aws $HOME/.aws ${LXC_AWS}
    ci_lxc_mount ${LXC_RUNNER_NAME} ssh $HOME/.ssh ${LXC_SSH}

    # Install runtime dependencies in the container
    ci_lxc_apt_install ${LXC_RUNNER_NAME} pip python3-venv libffi-dev
    ci_lxc_juju_snaps ${LXC_RUNNER_NAME}
}


ci_lxc_juju_snaps()
{
    # Install the host's juju snaps into the lxc runner
    local lxc_container=$1
    while read -r name _ _ track _ ; do
        ci_lxc_snap_install ${lxc_container} ${name} --channel=${track} --classic < /dev/null
    done < <(snap list | grep juju)
}


ci_lxc_job_run()
{
    # Run the job script inside the lxc runner
    local lxc_container=${BUILD_TAG}
    local lxc_workspace=/home/ubuntu/workspace

    ci_lxc_exec_user ${lxc_container} --cwd=${lxc_workspace} --env WORKSPACE=${lxc_workspace} $@
}