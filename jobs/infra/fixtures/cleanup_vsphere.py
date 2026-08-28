#!/usr/bin/env python

import argparse
import logging
import os
from pathlib import Path
import requests
import time
import urllib3
import yaml
from typing import Set
from dataclasses import dataclass
from vmware.vapi.vsphere.client import create_vsphere_client


session = requests.session()

# Disable cert verification and secure connection warning
session.verify = False
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
logging.basicConfig(level=logging.INFO)
log = logging.getLogger()


class InvalidCreds(Exception):
    """Raised when the credentials to vsphere aren't found."""


class FolderMatch(Exception):
    """Raised when not 1 folder matches the search."""


@dataclass
class Creds:
    vc_ip: str
    username: str
    password: str
    vmfolder: str

    @classmethod
    def from_juju(cls) -> "Creds":
        juju_path = Path(os.environ["HOME"], ".local", "share", "juju")
        juju_cred = juju_path / "credentials.yaml"
        juju_cloud = juju_path / "clouds.yaml"
        if not juju_cred.exists():
            raise InvalidCreds(f"{juju_cred} not found")
        if not juju_cloud.exists():
            raise InvalidCreds(f"{juju_cloud} not found")
        creds = yaml.safe_load(juju_cred.read_text())
        cloud = yaml.safe_load(juju_cloud.read_text())
        try:
            vsphere_cred = creds["credentials"]["vsphere"]
            vsphere_cloud = cloud["clouds"]["vsphere"]
        except KeyError as ex:
            raise InvalidCreds(
                "vsphere creds not found in juju credentials/clouds"
            ) from ex

        if "endpoint" not in vsphere_cloud:
            raise InvalidCreds("valid vsphere cloud not found")

        for user in vsphere_cred.values():
            if all(_ in user for _ in ["user", "password", "vmfolder"]):
                return cls(
                    vsphere_cloud["endpoint"],
                    user["user"],
                    user["password"],
                    user["vmfolder"],
                )
        raise InvalidCreds("valid vsphere creds not found")


class VsphereActions:
    def __init__(self, client, dry_run=True):
        self.client = client.vcenter
        self.dry_run = dry_run

    def locate_folder(self, path: str):
        """Find one vsphere folder at a specified path"""
        prior = None
        for node in path.split("/"):
            _filter = {"names": {node}}
            if prior:
                _filter["parent_folders"] = {_.folder for _ in prior}
            name_matches = self.client.Folder.list(filter=_filter)
            if not name_matches:
                raise FolderMatch(f"Cannot find {path}, {node} doesn't exist")
            prior = name_matches

        if len(name_matches) != 1:
            raise FolderMatch(f"Cannot find {path} exact match")
        return set(name_matches)

    def subfolders(self, parents: Set):
        """Find all subfolders of provided parents."""
        children = self.client.Folder.list(
            filter={"parent_folders": {_.folder for _ in parents}}
        )
        if not children:
            return set(parents)
        descendents = self.subfolders(children)
        return set(children) | descendents

    def child_vms(self, folders):
        return set(self.client.VM.list(filter={"folders": {_.folder for _ in folders}}))

    def shutdown_vms(self, vms):
        for vm in vms:
            if vm.power_state == "POWERED_ON":
                if not self.dry_run:
                    log.info(f"Powering off '{vm.name}'")
                    self.client.vm.guest.Power.shutdown(vm.vm)
                else:
                    log.info(f"DRYRUN: Would poweroff '{vm.name}'")

    def wait_folder_shutdown(self, folders):
        while vms := self.client.VM.list(
            filter=dict(
                folders={_.folder for _ in folders}, power_states={"POWERED_ON"}
            )
        ):
            log.info(f"Waiting for '{len(vms)}' to power off...")
            vm_names = "\n - ".join([vm.name for vm in vms])
            log.info(f"Set of VMs {vm_names}")
            time.sleep(5)

    def delete_vms(self, vms):
        for vm in vms:
            if not self.dry_run:
                log.info(f"Deleting '{vm.name}'")
                self.client.VM.delete(vm.vm)
            else:
                log.info(f"DRYRUN: Would delete '{vm.name}'")

    def cleanup(self, path):
        # locate a single folder matching the path in vmfolder
        parent = self.locate_folder(path)
        # find all subfolders within this parent path
        subfolders = self.subfolders(parent)
        for folder in subfolders:
            log.info(f"Searching for VMs in '{folder.name}'")
        # find all vms in any subfolders
        vms = self.child_vms(subfolders)
        # guest shutdown all those vms
        self.shutdown_vms(vms)
        if not self.dry_run:
            self.wait_folder_shutdown(subfolders)
        # delete all those vms
        self.delete_vms(vms)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--dry-run",
        dest="dry_run",
        action="store_true",
        help="If enabled, only log what would be shutdown and deleted.",
    )
    parser.add_argument(
        "--vmfolder",
        dest="vmfolder",
        help="override the vmfolder to delete",
        default=None,
    )
    args = parser.parse_args()
    # gather creds from juju config files
    creds = Creds.from_juju()
    # Connect to a vCenter Server and clean up
    _client = create_vsphere_client(
        server=creds.vc_ip,
        username=creds.username,
        password=creds.password,
        session=session,
    )
    vsphere = VsphereActions(_client, dry_run=args.dry_run)
    vsphere.cleanup(args.vmfolder or creds.vmfolder)
