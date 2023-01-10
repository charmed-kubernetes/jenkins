#!/usr/bin/env python3

import json
import os
import boto3
from subprocess import check_output, CalledProcessError

REGION = "us-east-1"

session = boto3.Session(profile_name="default", region_name=REGION)
ec2 = session.client("ec2")


def log(msg):
    print(msg, flush=True)


def sh(*args, **kwargs):
    log("+ " + " ".join(args[0]))
    try:
        output = check_output(*args, **kwargs).decode("UTF-8")
    except CalledProcessError as e:
        log(e.output)
        raise
    log(output)
    return output


def juju(cmd, *args, json=True):
    model = os.environ["JUJU_MODEL"]
    controller = os.environ["JUJU_CONTROLLER"]
    cmd = ["juju", cmd, "-m", f"{controller}:{model}"] + list(args)
    return sh(cmd)


def juju_json(cmd, *args):
    args = ["--format", "json"] + list(args)
    output = juju(cmd, *args)
    return json.loads(output)


def main():
    status = juju_json("status")
    units = list(status["applications"]["kubernetes-control-plane"]["units"].values())
    units += list(status["applications"]["kubernetes-worker"]["units"].values())
    machine_ids = list(unit["machine"] for unit in units)
    instance_ids = [
        status["machines"][machine_id]["instance-id"] for machine_id in machine_ids
    ]
    instance_subnet_pairs = []
    for instance_id in instance_ids:
        reservations = ec2.describe_instances(InstanceIds=[instance_id])["Reservations"]
        for reservation in reservations:
            instances = reservation["Instances"]
            for instance in instances:
                subnet_id = instance["SubnetId"]
                instance_subnet_pairs.append((instance_id, subnet_id))
    for instance_id, subnet_id in instance_subnet_pairs:
        log("Adding network interface to instance " + instance_id)
        log("  Creating network interface")
        response = ec2.create_network_interface(SubnetId=subnet_id)
        network_interface_id = response["NetworkInterface"]["NetworkInterfaceId"]
        log("  Network interface ID: " + network_interface_id)
        log("  Attaching network interface")
        response = ec2.attach_network_interface(
            NetworkInterfaceId=network_interface_id,
            InstanceId=instance_id,
            DeviceIndex=1,
        )
        attachment_id = response["AttachmentId"]
        log("  Attachment ID: " + attachment_id)
        log("  Setting DeleteOnTermination for attachment")
        ec2.modify_network_interface_attribute(
            NetworkInterfaceId=network_interface_id,
            Attachment={"AttachmentId": attachment_id, "DeleteOnTermination": True},
        )


if __name__ == "__main__":
    main()
