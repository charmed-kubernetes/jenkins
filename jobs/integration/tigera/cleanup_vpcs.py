#!/usr/bin/env python3.6

import json
import os
from pprint import pprint
from subprocess import check_output, CalledProcessError

REGION = "us-east-2"


def aws(*args, ignore_errors=False):
    cmd = ["aws", "--region", REGION, "--output", "json"] + list(args)
    print("+ " + " ".join(cmd))
    try:
        output = check_output(cmd)
    except CalledProcessError as e:
        print(e.output)
        if ignore_errors:
            return
        else:
            raise
    try:
        data = json.loads(output)
        pprint(data)
        return data
    except json.decoder.JSONDecodeError:
        if output:
            print(output)
        return


owner = os.environ.get("JOB_NAME", "test-calico")
gateways = aws("ec2", "describe-internet-gateways")["InternetGateways"]
for gateway in gateways:
    for tag in gateway.get("Tags", []):
        if tag["Key"] == "created-by" and tag["Value"] == owner:
            gateway_id = gateway["InternetGatewayId"]
            for attachment in gateway["Attachments"]:
                aws(
                    "ec2",
                    "detach-internet-gateway",
                    "--internet-gateway-id",
                    gateway_id,
                    "--vpc-id",
                    attachment["VpcId"],
                    ignore_errors=True,
                )
            aws(
                "ec2",
                "delete-internet-gateway",
                "--internet-gateway-id",
                gateway_id,
                ignore_errors=True,
            )
            break

subnets = aws("ec2", "describe-subnets")["Subnets"]
for subnet in subnets:
    for tag in subnet.get("Tags", []):
        if tag["Key"] == "created-by" and tag["Value"] == owner:
            aws(
                "ec2",
                "delete-subnet",
                "--subnet-id",
                subnet["SubnetId"],
                ignore_errors=True,
            )
            break

vpcs = aws("ec2", "describe-vpcs")["Vpcs"]
for vpc in vpcs:
    for tag in vpc.get("Tags", []):
        if tag["Key"] == "created-by" and tag["Value"] == owner:
            aws("ec2", "delete-vpc", "--vpc-id", vpc["VpcId"], ignore_errors=True)
            break
