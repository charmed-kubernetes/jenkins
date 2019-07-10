#!/usr/bin/env python3.6

import argparse
import json
import time
from subprocess import check_output, check_call


MODEL = None
REGION = None


def log(msg):
    print(msg, flush=True)


def get_juju_status():
    cmd = ["juju", "status", "--format", "json", "-m", MODEL]
    output = check_output(cmd, encoding="UTF-8")
    status = json.loads(output)
    return status


def get_instance_id(machine_id):
    log("Getting instance ID for machine " + machine_id)
    while True:
        status = get_juju_status()
        machines = status["machines"]
        if machine_id not in machines:
            log("WARNING: machine %s disappeared" % machine_id)
            return None
        machine = machines[machine_id]
        if machine["instance-id"] == "pending":
            time.sleep(1)
            continue
        return machine["instance-id"]


def disable_source_dest_check_on_instance(instance_id):
    log("Disabling source dest check on instance " + instance_id)
    cmd = [
        "aws",
        "--region",
        REGION,
        "ec2",
        "modify-instance-attribute",
        "--instance-id",
        instance_id,
        "--source-dest-check",
        '{"Value": false}',
    ]
    log("+ " + " ".join(cmd))
    check_call(cmd)


def disable_source_dest_check():
    status = get_juju_status()
    for machine_id in status["machines"]:
        instance_id = get_instance_id(machine_id)
        if instance_id:
            disable_source_dest_check_on_instance(instance_id)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("-m", "--model", required=True)
    args = parser.parse_args()

    global MODEL
    MODEL = args.model

    status = get_juju_status()

    if status["model"]["cloud"] != "aws":
        log("Cloud is not AWS, doing nothing")
        return

    apps = ["calico", "tigera-secure-ee"]
    if not any(app in status["applications"] for app in apps):
        log("No apps need source dest check disabled, doing nothing")
        return

    global REGION
    REGION = status["model"]["region"]

    disable_source_dest_check()


main()
