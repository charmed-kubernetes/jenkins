#!/usr/bin/env python3

import argparse
import ipaddress
import json
import os
import tempfile
import time
import yaml
from subprocess import check_output, check_call, CalledProcessError

VPC_CIDR = "172.30.0.0/16"
SUBNET_CIDRS = ["172.30.0.0/24", "172.30.1.0/24"]
REGION = "us-east-2"
AVAILABILITY_ZONE = "us-east-2a"
BIRD_CONFIG_BASE = """
log syslog all;
debug protocols all;

router id %s;

protocol kernel {
  persist;
  scan time 20;
  export all;
}

protocol device {
  scan time 10;
}
"""
BIRD_CONFIG_PEER = """
protocol bgp {
  import all;
  local as 64512;
  neighbor %s as 64512;
  direct;
}
"""

command_defs = {}


def def_command(name):
    def decorator(f):
        command_defs[name] = f

    return decorator


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


def ec2(*args, ignore_errors=False):
    cmd = ["aws", "--region", REGION, "--output", "json", "ec2"] + list(args)
    try:
        output = sh(cmd)
    except CalledProcessError:
        if ignore_errors:
            return
        else:
            raise
    try:
        data = json.loads(output)
        return data
    except json.decoder.JSONDecodeError:
        return


def tag_resource(resource_id):
    owner = os.environ.get("JOB_NAME", "test-calico")
    ec2(
        "create-tags",
        "--resource",
        resource_id,
        "--tags",
        "Key=created-by,Value=" + owner,
    )


def juju(cmd, *args, json=True):
    model = os.environ["JUJU_MODEL"]
    controller = os.environ["JUJU_CONTROLLER"]
    cmd = ["juju", cmd, "-m", f"{controller}:{model}"] + list(args)
    return sh(cmd)


def juju_json(cmd, *args):
    args = ["--format", "json"] + list(args)
    output = juju(cmd, *args)
    return json.loads(output)


def get_instance_id(machine_id):
    log("Getting instance ID for machine " + machine_id)
    while True:
        status = juju_json("status")
        machines = status["machines"]
        if machine_id not in machines:
            log("WARNING: machine %s disappeared" % machine_id)
            return None
        machine = machines[machine_id]
        if machine["instance-id"] == "pending":
            time.sleep(1)
            continue
        return machine["instance-id"]


@def_command("bootstrap")
def bootstrap():
    # Create VPC
    vpc_id = ec2("create-vpc", "--cidr", VPC_CIDR)["Vpc"]["VpcId"]
    tag_resource(vpc_id)
    ec2("modify-vpc-attribute", "--vpc-id", vpc_id, "--enable-dns-support")
    ec2("modify-vpc-attribute", "--vpc-id", vpc_id, "--enable-dns-hostnames")

    # Create subnets
    num_subnets = os.environ.get("NUM_SUBNETS")
    num_subnets = int(num_subnets) if num_subnets else 1
    subnet_cidrs = SUBNET_CIDRS[:num_subnets]
    for subnet_cidr in subnet_cidrs:
        subnet_id = ec2(
            "create-subnet",
            "--vpc-id",
            vpc_id,
            "--cidr-block",
            subnet_cidr,
            "--availability-zone",
            AVAILABILITY_ZONE,
        )["Subnet"]["SubnetId"]
        tag_resource(subnet_id)
        ec2(
            "modify-subnet-attribute",
            "--subnet-id",
            subnet_id,
            "--map-public-ip-on-launch",
        )

    # Create gateway
    gateway_id = ec2("create-internet-gateway")["InternetGateway"]["InternetGatewayId"]
    tag_resource(gateway_id)
    ec2("attach-internet-gateway", "--vpc-id", vpc_id, "--internet-gateway", gateway_id)

    # Create route
    route_table_ids = []
    route_tables = ec2("describe-route-tables")["RouteTables"]
    for route_table in route_tables:
        if route_table["VpcId"] == vpc_id:
            route_table_id = route_table["RouteTableId"]
            tag_resource(route_table_id)
            route_table_ids.append(route_table_id)
    for route_table_id in route_table_ids:
        ec2(
            "create-route",
            "--route-table-id",
            route_table_id,
            "--destination-cidr-block",
            "0.0.0.0/0",
            "--gateway-id",
            gateway_id,
        )

    # Juju bootstrap
    controller_name = os.environ.get("JUJU_CONTROLLER", "aws-" + vpc_id)
    check_call(
        [
            "juju",
            "bootstrap",
            "aws/" + REGION,
            controller_name,
            "--config",
            "vpc-id=" + vpc_id,
            "--to",
            "subnet=" + subnet_cidrs[0],
            "--config",
            "test-mode=true",
        ]
    )
    check_call(["juju", "model-defaults", "vpc-id=" + vpc_id, "test-mode=true"])


@def_command("cleanup")
def cleanup():
    owner = os.environ.get("JOB_NAME", "test-calico")
    network_interfaces = ec2("describe-network-interfaces")["NetworkInterfaces"]
    for network_interface in network_interfaces:
        for tag in network_interface.get("TagSet", []):
            if tag["Key"] == "created-by" and tag["Value"] == owner:
                network_interface_id = network_interface["NetworkInterfaceId"]
                ec2(
                    "delete-network-interface",
                    "--network-interface-id",
                    network_interface_id,
                    ignore_errors=True,
                )
                break

    gateways = ec2("describe-internet-gateways")["InternetGateways"]
    for gateway in gateways:
        for tag in gateway.get("Tags", []):
            if tag["Key"] == "created-by" and tag["Value"] == owner:
                gateway_id = gateway["InternetGatewayId"]
                for attachment in gateway["Attachments"]:
                    ec2(
                        "detach-internet-gateway",
                        "--internet-gateway-id",
                        gateway_id,
                        "--vpc-id",
                        attachment["VpcId"],
                        ignore_errors=True,
                    )
                ec2(
                    "delete-internet-gateway",
                    "--internet-gateway-id",
                    gateway_id,
                    ignore_errors=True,
                )
                break

    subnets = ec2("describe-subnets")["Subnets"]
    for subnet in subnets:
        for tag in subnet.get("Tags", []):
            if tag["Key"] == "created-by" and tag["Value"] == owner:
                ec2(
                    "delete-subnet",
                    "--subnet-id",
                    subnet["SubnetId"],
                    ignore_errors=True,
                )
                break

    vpcs = ec2("describe-vpcs")["Vpcs"]
    for vpc in vpcs:
        for tag in vpc.get("Tags", []):
            if tag["Key"] == "created-by" and tag["Value"] == owner:
                ec2("delete-vpc", "--vpc-id", vpc["VpcId"], ignore_errors=True)
                break


def disable_source_dest_check_on_instance(instance_id):
    log("Getting network interfaces for instance " + instance_id)
    network_interface_ids = []
    reservations = ec2(
        "describe-instances", "--filter", "Name=instance-id,Values=" + instance_id
    )["Reservations"]
    for reservation in reservations:
        instances = reservation["Instances"]
        for instance in instances:
            for network_interface in instance["NetworkInterfaces"]:
                network_interface_id = network_interface["NetworkInterfaceId"]
                network_interface_ids.append(network_interface_id)

    for network_interface_id in network_interface_ids:
        log("Disabling source/dest checks on " + network_interface_id)

        ec2(
            "modify-network-interface-attribute",
            "--network-interface-id",
            network_interface_id,
            "--source-dest-check",
            '{"Value": false}',
        )


@def_command("disable-source-dest-check")
def disable_source_dest_check():
    status = juju_json("status")

    if status["model"]["cloud"] != "aws":
        log("Cloud is not AWS, doing nothing")
        return

    apps = ["calico", "tigera-secure-ee"]
    if not any(app in status["applications"] for app in apps):
        log("No apps need source dest check disabled, doing nothing")
        return

    global REGION
    REGION = status["model"]["region"]

    status = juju_json("status")
    for machine_id in status["machines"]:
        instance_id = get_instance_id(machine_id)
        if instance_id:
            disable_source_dest_check_on_instance(instance_id)


def get_model_vpc_id():
    log("Getting VPC ID")
    model_config = juju_json("model-config")
    vpc_id = model_config["vpc-id"]["Value"]
    return vpc_id


def get_subnets_in_vpc(vpc_id):
    log("Getting subnets in VPC " + vpc_id)
    subnets = ec2("describe-subnets")["Subnets"]
    subnets = [subnet for subnet in subnets if subnet["VpcId"] == vpc_id]
    return subnets


def get_instance_ips(instance_id):
    log("Getting IPs for instance " + instance_id)
    ips = set()
    reservations = ec2(
        "describe-instances", "--filter", "Name=instance-id,Values=" + instance_id
    )["Reservations"]
    for reservation in reservations:
        for instance in reservation["Instances"]:
            for interface in instance["NetworkInterfaces"]:
                ip = interface["PrivateIpAddress"]
                ips.add(ip)
    return ips


def get_machine_id(unit_name):
    log("Getting machine ID for unit " + unit_name)
    application = unit_name.split("/")[0]
    while True:
        status = juju_json("status")
        machine_id = status["applications"][application]["units"][unit_name].get(
            "machine"
        )
        if machine_id:
            return machine_id
        time.sleep(1)


@def_command("deploy-bgp-router")
def deploy_bgp_router():
    vpc_id = get_model_vpc_id()
    subnets = get_subnets_in_vpc(vpc_id)

    log("Deploying router to first subnet")
    juju("deploy", "ubuntu", "router", "--to", "subnet=" + subnets[0]["CidrBlock"])
    machine_id = get_machine_id("router/0")
    instance_id = get_instance_id(machine_id)

    log("Getting instance security groups")
    security_groups = set()
    reservations = ec2(
        "describe-instances", "--filter", "Name=instance-id,Values=" + instance_id
    )["Reservations"]
    for reservation in reservations:
        for instance in reservation["Instances"]:
            for group in instance["SecurityGroups"]:
                security_groups.add(group["GroupId"])

    log("Adding router to remaining subnets")
    for i in range(1, len(subnets)):
        subnet = subnets[i]
        subnet_id = subnet["SubnetId"]
        result = ec2(
            "create-network-interface",
            "--subnet-id",
            subnet_id,
            "--groups",
            json.dumps(list(security_groups)),
        )
        network_interface_id = result["NetworkInterface"]["NetworkInterfaceId"]
        tag_resource(network_interface_id)
        attachment_id = ec2(
            "attach-network-interface",
            "--network-interface-id",
            network_interface_id,
            "--instance-id",
            instance_id,
            "--device-index",
            str(i),
        )["AttachmentId"]
        ec2(
            "modify-network-interface-attribute",
            "--network-interface-id",
            network_interface_id,
            "--attachment",
            "AttachmentId=%s,DeleteOnTermination=true" % attachment_id,
        )

    log("Waiting for router to come up")
    juju("run", "--unit", "router/0", "echo", "ready")

    log("Enabling secondary network interfaces")
    for i in range(1, len(subnets)):
        interface = "ens%d" % (i + 5)
        # Setting IF_METRIC=101 lowers the priority of the routes for this network
        # interface. We need the primary network's default route to be higher
        # priority so that the public/elastic IP, which is bound to the primary
        # network interface, continues to work.
        juju(
            "ssh",
            "router/0",
            "sudo",
            "dhclient",
            interface,
            "-e",
            "IF_METRIC=101",
            json=False,
        )

    log("Installing BIRD")
    juju("ssh", "router/0", "sudo", "apt", "update", json=False)
    juju("ssh", "router/0", "sudo", "apt", "install", "-y", "bird", json=False)

    log("Getting VPC CIDR")
    vpc = ec2("describe-vpcs", "--filter", "Name=vpc-id,Values=" + vpc_id)["Vpcs"][0]
    vpc_cidr = vpc["CidrBlock"]

    log("Getting router IPs")
    router_ips = get_instance_ips(instance_id)

    log("Configuring cloudinit-userdata to modify route tables")
    cmd = "for ip in %s; do ip route add %s via $ip || true; done" % (
        " ".join(router_ips),
        vpc_cidr,
    )
    juju("model-config", 'cloudinit-userdata="{postruncmd: [\\"%s\\"]}"' % cmd)


@def_command("configure-bgp")
def configure_bgp():
    # Get subnets
    vpc_id = get_model_vpc_id()
    subnets = get_subnets_in_vpc(vpc_id)

    # Get Router IP for each subnet
    router_machine_id = get_machine_id("router/0")
    router_instance_id = get_instance_id(router_machine_id)
    router_ips = get_instance_ips(router_instance_id)

    # Get kubernetes-master IPs
    master_ips = set()
    for unit_name in ["kubernetes-master/0", "kubernetes-master/1"]:
        machine_id = get_machine_id(unit_name)
        instance_id = get_instance_id(machine_id)
        ips = get_instance_ips(instance_id)
        master_ips.update(ips)

    # Get kubernetes-master calico unit IDs
    master_calico_units = []
    for unit_name in ["kubernetes-master/0", "kubernetes-master/1"]:
        log("Getting calico unit attached to " + unit_name)
        while True:
            status = juju_json("status")
            unit = status["applications"]["kubernetes-master"]["units"][unit_name]
            subordinate_names = [
                name
                for name in unit.get("subordinates", [])
                if name.startswith("calico/")
            ]
            if subordinate_names:
                master_calico_units.append(subordinate_names[0])
                break
            time.sleep(1)

    # Configure Calico
    subnet_bgp_peers = {}
    for subnet in subnets:
        cidr = subnet["CidrBlock"]
        network = ipaddress.ip_network(cidr)
        ips = [ipaddress.ip_address(ip) for ip in router_ips]
        ips = [ip for ip in ips if ip in network]
        ips = [str(ip) for ip in ips]
        assert len(ips) == 1, "WHUT? %s" % ips
        ip = ips[0]
        subnet_bgp_peers[cidr] = [{"address": ip, "as-number": 64512}]

    unit_numbers = [int(unit_name.split("/")[1]) for unit_name in master_calico_units]
    route_reflector_cluster_ids = {
        unit_number: "0.0.0.0" for unit_number in unit_numbers
    }

    global_bgp_peers = [
        {"address": address, "as-number": 64512} for address in master_ips
    ]

    juju(
        "config",
        "calico",
        "subnet-bgp-peers=" + yaml.dump(subnet_bgp_peers),
        "route-reflector-cluster-ids=" + yaml.dump(route_reflector_cluster_ids),
        "global-bgp-peers=" + yaml.dump(global_bgp_peers),
        "node-to-node-mesh=false",
    )

    # Get all Calico IPs
    calico_ips = set()
    calico_ips.update(master_ips)
    status = juju_json("status")
    for unit_name in status["applications"]["kubernetes-worker"]["units"]:
        machine_id = get_machine_id(unit_name)
        instance_id = get_instance_id(machine_id)
        ips = get_instance_ips(instance_id)
        calico_ips.update(ips)

    # Configure BIRD
    bird_conf = BIRD_CONFIG_BASE % list(router_ips)[0]
    for ip in calico_ips:
        bird_conf += BIRD_CONFIG_PEER % ip
    with tempfile.NamedTemporaryFile("w") as f:
        f.write(bird_conf)
        f.flush()
        juju("scp", f.name, "router/0:bird.conf")
    juju("ssh", "router/0", "sudo", "cp", "bird.conf", "/etc/bird/bird.conf")
    juju("ssh", "router/0", "sudo", "service", "bird", "restart")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=command_defs)
    args = parser.parse_args()
    command_defs[args.command]()


main()
