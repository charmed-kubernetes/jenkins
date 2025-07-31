#!/bin/bash

THISDIR="$(dirname "$(realpath "$0")")"

if [[ $0 == $BASH_SOURCE ]]; then
  echo "$0 should be sourced";
  exit
fi
echo "sourced ${BASH_SOURCE:-$0}"


function purge::vsphere
{
    tox -e py -- pip install --upgrade git+https://github.com/vmware/vsphere-automation-sdk-python.git
    tox -e py -- python ${THISDIR}/cleanup_vsphere.py --dry-run --vmfolder=k8s-ci-root
}
